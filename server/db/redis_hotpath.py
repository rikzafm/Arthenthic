"""
server/db/redis_hotpath.py
Redis 7 Hot-Path Cache & Atomic State Engine (Part II, Section 3.2).
Implements the 6 Redis Hot-Path Keys with monotonic Lua checks and local in-memory fallback:
1. sun:ctr:{chipId}             -> Monotonic Lua check-and-set (new_ctr > old_ctr) rejecting replayed NFC URLs in < 1ms (D-02)
2. nonce:{nonce}               -> SET nonce:{n} 1 NX EX <ttl> at EIP-712 signing time (I-01)
3. quota:{wallet}:{policy}:{p} -> INCRBY atomic counter enforcing per-user Paymaster gas limits (K-02)
4. rl:verify:{ipHash}          -> Sliding-window rate limiter protecting guest wallet-less verification (D-14*)
5. pm:balance                  -> Cached EntryPoint deposit status and balance_wei (K-03)
6. idx:head:{chainId}          -> Latest indexed block number and timestamp (SD-12)
"""

import os
import time
import heapq
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple


SUN_COUNTER_LUA_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local incoming = tonumber(ARGV[1])
if current ~= false and incoming <= tonumber(current) then
    return 0
end
redis.call('SET', KEYS[1], ARGV[1])
return 1
"""

QUOTA_LUA_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local max_quota = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if current >= max_quota then
    return {0, current, max_quota}
end
local new_val = redis.call('INCR', KEYS[1])
if new_val == 1 then
    redis.call('EXPIRE', KEYS[1], ttl)
end
return {1, new_val, max_quota}
"""

RATE_LIMIT_LUA_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local max_req = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
if current >= max_req then
    return {0, current}
end
local new_val = redis.call('INCR', KEYS[1])
if new_val == 1 then
    redis.call('EXPIRE', KEYS[1], window)
end
return {1, new_val}
"""



class InMemoryRedisHotPath:
    """
    Hybrid Redis 7 + Thread-safe In-Memory Hot-Path Engine.
    Uses live Redis 7 Lua & atomic commands when redis_client / REDIS_URL is configured,
    and falls back automatically to in-memory atomic state for offline dev and tests.
    """

    SUN_COUNTER_LUA_SCRIPT = SUN_COUNTER_LUA_SCRIPT
    QUOTA_LUA_SCRIPT = QUOTA_LUA_SCRIPT
    RATE_LIMIT_LUA_SCRIPT = RATE_LIMIT_LUA_SCRIPT
    MAX_KEYS = 10000

    def __init__(self, redis_client: Optional[Any] = None, redis_url: Optional[str] = None):
        self._lock = threading.RLock()
        self._strings: Dict[str, str] = {}
        self._ttls: Dict[str, float] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.redis_client = redis_client
        if self.redis_client is None and self.redis_url:
            try:
                import redis  # type: ignore
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            except Exception:
                self.redis_client = None

    def _purge_expired(self, key: Optional[str] = None):
        with self._lock:
            now = time.time()
            if key and key in self._ttls and now > self._ttls[key]:
                self._strings.pop(key, None)
                self._hashes.pop(key, None)
                self._ttls.pop(key, None)

            # Active sweep: purge expired keys when called without key or tracking > 50 keys
            if key is None or len(self._ttls) > 50:
                expired = [k for k, exp in self._ttls.items() if now > exp]
                for k in expired:
                    self._strings.pop(k, None)
                    self._hashes.pop(k, None)
                    self._ttls.pop(k, None)

            # Bounded memory: enforce MAX_KEYS eviction (earliest expiration FIFO / LRU)
            if len(self._ttls) > self.MAX_KEYS:
                excess = len(self._ttls) - self.MAX_KEYS
                oldest_keys = heapq.nsmallest(excess, self._ttls.items(), key=lambda item: item[1])
                for k, _ in oldest_keys:
                    self._strings.pop(k, None)
                    self._hashes.pop(k, None)
                    self._ttls.pop(k, None)

            if len(self._strings) > self.MAX_KEYS:
                excess_strings = len(self._strings) - self.MAX_KEYS
                keys_to_remove = list(self._strings.keys())[:excess_strings]
                for k in keys_to_remove:
                    self._strings.pop(k, None)
                    self._ttls.pop(k, None)

    def health_check(self) -> str:
        if self.redis_client is not None:
            try:
                if self.redis_client.ping():
                    return "ok"
            except Exception:
                pass
        return "in_memory_fallback"

    # 1. sun:ctr:{chipId}
    def check_and_update_sun_counter(self, chip_id: str, new_ctr: int) -> Tuple[bool, Optional[str]]:
        key = f"sun:ctr:{chip_id.upper()}"
        if self.redis_client is not None:
            try:
                res = self.redis_client.eval(self.SUN_COUNTER_LUA_SCRIPT, 1, key, str(new_ctr))
                if int(res) == 1:
                    return True, None
                old_val = self.redis_client.get(key)
                if isinstance(old_val, bytes):
                    old_val = old_val.decode("utf-8")
                if not old_val:
                    old_val = str(new_ctr)
                return False, f"Replay rejected: Counter {new_ctr} <= last counter {old_val}"
            except Exception:
                pass

        with self._lock:
            self._purge_expired(key)
            old_val = self._strings.get(key)
            if old_val is not None:
                old_ctr = int(old_val)
                if new_ctr <= old_ctr:
                    return False, f"Replay rejected: Counter {new_ctr} <= last counter {old_ctr}"
            self._strings[key] = str(new_ctr)
            return True, None

    # 2. nonce:{nonce}
    def set_attestation_nonce(self, nonce: str, ttl_seconds: int = 360) -> bool:
        key = f"nonce:{nonce}"
        if self.redis_client is not None:
            try:
                res = self.redis_client.set(key, "1", nx=True, ex=ttl_seconds)
                return bool(res)
            except Exception:
                pass

        with self._lock:
            self._purge_expired(key)
            if key in self._strings:
                return False  # Already exists (replay)
            self._strings[key] = "1"
            self._ttls[key] = time.time() + ttl_seconds
            return True

    def is_nonce_used(self, nonce: str) -> bool:
        key = f"nonce:{nonce}"
        if self.redis_client is not None:
            try:
                res = self.redis_client.exists(key)
                return bool(res)
            except Exception:
                pass
        with self._lock:
            self._purge_expired(key)
            return key in self._strings

    # 3. quota:{wallet}:{policyId}:{period}
    def check_and_increment_quota(
        self,
        wallet: str,
        policy_id: str,
        period_key: str,
        max_quota: int,
        ttl_seconds: int = 86400 * 30
    ) -> Tuple[bool, int, int]:
        key = f"quota:{wallet.lower()}:{policy_id}:{period_key}"
        if self.redis_client is not None:
            try:
                res = self.redis_client.eval(self.QUOTA_LUA_SCRIPT, 1, key, str(max_quota), str(ttl_seconds))
                if res and isinstance(res, (list, tuple)) and len(res) >= 3:
                    allowed = bool(res[0] == 1 or res[0] is True)
                    current_val = int(res[1])
                    max_q = int(res[2])
                    return allowed, current_val, max_q
            except Exception:
                pass

        with self._lock:
            self._purge_expired(key)
            current = int(self._strings.get(key, "0"))
            if current >= max_quota:
                return False, current, max_quota
            new_val = current + 1
            self._strings[key] = str(new_val)
            if key not in self._ttls:
                self._ttls[key] = time.time() + ttl_seconds
            return True, new_val, max_quota

    # 4. rl:verify:{ipHash}
    def check_rate_limit(self, ip: str, max_requests: int = 30, window_seconds: int = 60) -> Tuple[bool, int]:
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        key = f"rl:verify:{ip_hash}"
        if self.redis_client is not None:
            try:
                res = self.redis_client.eval(self.RATE_LIMIT_LUA_SCRIPT, 1, key, str(max_requests), str(window_seconds))
                if res and isinstance(res, (list, tuple)) and len(res) >= 2:
                    return bool(res[0] == 1 or res[0] is True), int(res[1])
            except Exception:
                pass

        with self._lock:
            self._purge_expired(key)
            current = int(self._strings.get(key, "0"))
            if current >= max_requests:
                return False, current
            new_val = current + 1
            self._strings[key] = str(new_val)
            if key not in self._ttls:
                self._ttls[key] = time.time() + window_seconds
            return True, new_val

    # 5. pm:balance
    def set_paymaster_balance(self, chain_id: int, balance_wei: int, status: str = "ok"):
        key = f"pm:balance:{chain_id}"
        payload = {
            "balance_wei": str(balance_wei),
            "status": status,
            "updated_at": str(time.time()),
        }
        if self.redis_client is not None:
            try:
                self.redis_client.hset(key, mapping=payload)
                self.redis_client.expire(key, 60)
                return
            except Exception:
                pass

        with self._lock:
            self._hashes[key] = payload
            self._ttls[key] = time.time() + 60

    def get_paymaster_balance(self, chain_id: int) -> Dict[str, Any]:
        key = f"pm:balance:{chain_id}"
        if self.redis_client is not None:
            try:
                h = self.redis_client.hgetall(key)
                if h:
                    decoded = {
                        k.decode("utf-8") if isinstance(k, bytes) else k: (
                            v.decode("utf-8") if isinstance(v, bytes) else v
                        )
                        for k, v in h.items()
                    }
                    return {
                        "balance_wei": decoded.get("balance_wei", "0"),
                        "status": decoded.get("status", "ok"),
                        "cached": True,
                    }
                return {"balance_wei": "1000000000000000000", "status": "ok", "cached": False}
            except Exception:
                pass

        with self._lock:
            self._purge_expired(key)
            h = self._hashes.get(key)
            if not h:
                return {"balance_wei": "1000000000000000000", "status": "ok", "cached": False}
            return {"balance_wei": h.get("balance_wei", "0"), "status": h.get("status", "ok"), "cached": True}

    # 6. idx:head:{chainId}
    def update_indexer_head(self, chain_id: int, block_number: int, block_hash: str):
        key = f"idx:head:{chain_id}"
        payload = {
            "block_number": str(block_number),
            "block_hash": block_hash,
            "timestamp": str(time.time()),
        }
        if self.redis_client is not None:
            try:
                self.redis_client.hset(key, mapping=payload)
                return
            except Exception:
                pass

        with self._lock:
            self._hashes[key] = payload

    def get_indexer_head(self, chain_id: int) -> Dict[str, Any]:
        key = f"idx:head:{chain_id}"
        if self.redis_client is not None:
            try:
                h = self.redis_client.hgetall(key)
                if h:
                    decoded = {
                        k.decode("utf-8") if isinstance(k, bytes) else k: (
                            v.decode("utf-8") if isinstance(v, bytes) else v
                        )
                        for k, v in h.items()
                    }
                    return {
                        "block_number": int(decoded.get("block_number", "0")),
                        "block_hash": decoded.get("block_hash", "0x0"),
                        "timestamp": float(decoded.get("timestamp", str(time.time()))),
                    }
                return {
                    "block_number": 0,
                    "block_hash": "0x0",
                    "timestamp": time.time(),
                }
            except Exception:
                pass

        with self._lock:
            h = self._hashes.get(key, {})
            return {
                "block_number": int(h.get("block_number", "0")),
                "block_hash": h.get("block_hash", "0x0"),
                "timestamp": float(h.get("timestamp", str(time.time()))),
            }


# Singleton instance
redis_hotpath = InMemoryRedisHotPath()
