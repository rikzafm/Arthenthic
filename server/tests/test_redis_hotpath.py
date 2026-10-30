"""
server/tests/test_redis_hotpath.py
Unit and concurrency tests for Redis Hotpath:
1. Atomic QUOTA_LUA_SCRIPT evaluation via Redis eval when connected.
2. In-memory fallback atomic quota enforcement.
3. Thread-safe concurrency under parallel workers.
4. Active sweep and bounded memory eviction eliminating unbounded key accumulation.
"""

import time
from unittest.mock import MagicMock
from concurrent.futures import ThreadPoolExecutor

from server.db.redis_hotpath import InMemoryRedisHotPath, QUOTA_LUA_SCRIPT, RATE_LIMIT_LUA_SCRIPT


def test_quota_lua_script_evaluation_live_redis():
    """Verifies QUOTA_LUA_SCRIPT is evaluated directly in Redis when redis_client is connected."""
    mock_redis = MagicMock()
    # Mock Redis eval returning [allowed=1, new_val=1, max_quota=5]
    mock_redis.eval.return_value = [1, 1, 5]

    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)
    allowed, current, max_quota = hotpath.check_and_increment_quota(
        wallet="0x1234567890123456789012345678901234567890",
        policy_id="T1",
        period_key="202610",
        max_quota=5,
    )

    assert allowed is True
    assert current == 1
    assert max_quota == 5
    assert mock_redis.eval.called
    args = mock_redis.eval.call_args[0]
    assert args[0] == QUOTA_LUA_SCRIPT

    # When quota is exceeded, Redis Lua script returns [0, 5, 5]
    mock_redis.eval.return_value = [0, 5, 5]
    allowed2, current2, max_quota2 = hotpath.check_and_increment_quota(
        wallet="0x1234567890123456789012345678901234567890",
        policy_id="T1",
        period_key="202610",
        max_quota=5,
    )
    assert allowed2 is False
    assert current2 == 5
    assert max_quota2 == 5


def test_in_memory_quota_enforcement_offline():
    """Verifies local fallback enforces quota ceiling correctly."""
    hotpath = InMemoryRedisHotPath(redis_client=None)
    wallet = "0xOfflineWallet0000000000000000000000001"

    for i in range(1, 4):
        allowed, val, max_q = hotpath.check_and_increment_quota(
            wallet=wallet, policy_id="T2", period_key="202610", max_quota=3
        )
        assert allowed is True
        assert val == i

    # 4th request must be rejected
    allowed, val, max_q = hotpath.check_and_increment_quota(
        wallet=wallet, policy_id="T2", period_key="202610", max_quota=3
    )
    assert allowed is False
    assert val == 3


def test_in_memory_thread_safe_concurrency():
    """
    Verifies that under heavy multi-threaded contention (10 threads, 50 requests),
    the atomic lock guarantees exactly max_quota increments succeed.
    """
    hotpath = InMemoryRedisHotPath(redis_client=None)
    wallet = "0xConcurrentUser00000000000000000000001"
    max_quota = 15

    results = []

    def task(_):
        return hotpath.check_and_increment_quota(
            wallet=wallet, policy_id="T1", period_key="202610_concurrent", max_quota=max_quota
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(task, range(50)))

    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]

    assert len(successes) == max_quota, f"Expected {max_quota} successes, got {len(successes)}"
    assert len(failures) == 50 - max_quota


def test_active_sweep_and_bounded_memory_eviction():
    """
    Verifies active sweep purges expired keys and bounds memory under MAX_KEYS.
    """
    hotpath = InMemoryRedisHotPath(redis_client=None)
    hotpath.MAX_KEYS = 50  # Reduced bound for test verification

    # Populate 100 ephemeral keys with past expiration (already expired)
    past_time = time.time() - 10
    for i in range(100):
        key = f"nonce:expired_{i}"
        hotpath._strings[key] = "1"
        hotpath._ttls[key] = past_time

    assert len(hotpath._ttls) == 100

    # Trigger purge
    hotpath._purge_expired()

    # Expired keys should be swept
    assert len(hotpath._ttls) == 0
    assert len(hotpath._strings) == 0

    # Populate 100 fresh keys (exceeding MAX_KEYS of 50)
    future_time = time.time() + 300
    for i in range(100):
        key = f"nonce:fresh_{i}"
        hotpath._strings[key] = "1"
        hotpath._ttls[key] = future_time + i

    hotpath._purge_expired()

    # Bounded to MAX_KEYS
    assert len(hotpath._ttls) <= 50
    assert len(hotpath._strings) <= 50


def test_paymaster_balance_live_redis_queries_hgetall():
    """Verifies get_paymaster_balance queries live Redis via hgetall."""
    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {"balance_wei": "500000000000000000", "status": "warning"}

    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)
    res = hotpath.get_paymaster_balance(84532)

    assert mock_redis.hgetall.called
    assert mock_redis.hgetall.call_args[0][0] == "pm:balance:84532"
    assert res["balance_wei"] == "500000000000000000"
    assert res["status"] == "warning"
    assert res["cached"] is True

    # Test byte-decoding
    mock_redis.hgetall.return_value = {b"balance_wei": b"2000000000000000000", b"status": b"ok"}
    res2 = hotpath.get_paymaster_balance(84532)
    assert res2["balance_wei"] == "2000000000000000000"
    assert res2["status"] == "ok"
    assert res2["cached"] is True

    # Test fallback to _hashes on Redis exception
    mock_redis.hgetall.side_effect = Exception("Redis connection lost")
    hotpath._hashes["pm:balance:84532"] = {"balance_wei": "100", "status": "critical"}
    res3 = hotpath.get_paymaster_balance(84532)
    assert res3["balance_wei"] == "100"
    assert res3["status"] == "critical"


def test_indexer_head_live_redis_queries_hgetall():
    """Verifies get_indexer_head queries live Redis via hgetall."""
    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {
        "block_number": "123456",
        "block_hash": "0xabc123def456",
        "timestamp": "1700000000.5",
    }

    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)
    res = hotpath.get_indexer_head(84532)

    assert mock_redis.hgetall.called
    assert mock_redis.hgetall.call_args[0][0] == "idx:head:84532"
    assert res["block_number"] == 123456
    assert res["block_hash"] == "0xabc123def456"
    assert res["timestamp"] == 1700000000.5

    # Test byte decoding
    mock_redis.hgetall.return_value = {
        b"block_number": b"654321",
        b"block_hash": b"0xdef456abc123",
        b"timestamp": b"1700000500.0",
    }
    res2 = hotpath.get_indexer_head(84532)
    assert res2["block_number"] == 654321
    assert res2["block_hash"] == "0xdef456abc123"
    assert res2["timestamp"] == 1700000500.0

    # Test fallback to _hashes on Redis exception
    mock_redis.hgetall.side_effect = Exception("Redis connection lost")
    hotpath._hashes["idx:head:84532"] = {
        "block_number": "999",
        "block_hash": "0xfallback",
        "timestamp": "1699999999.0",
    }
    res3 = hotpath.get_indexer_head(84532)
    assert res3["block_number"] == 999
    assert res3["block_hash"] == "0xfallback"


def test_is_nonce_used_returns_false_when_redis_exists_returns_zero():
    """Verifies is_nonce_used does not fall through to in-memory dict when Redis exists returns 0."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)

    # Set nonce via Redis
    res_set = hotpath.set_attestation_nonce("nonce_test", ttl_seconds=10)
    assert res_set is True
    assert mock_redis.set.called

    # When Redis reports key does NOT exist (0 / False)
    mock_redis.exists.return_value = 0
    assert hotpath.is_nonce_used("nonce_test") is False
    assert mock_redis.exists.called

    # Even if key somehow lingered in local _strings, live Redis assertion must govern
    hotpath._strings["nonce:nonce_test"] = "1"
    assert hotpath.is_nonce_used("nonce_test") is False

    # When Redis reports key DOES exist (1 / True)
    mock_redis.exists.return_value = 1
    assert hotpath.is_nonce_used("nonce_test") is True

    # When Redis raises exception, fallback to local _strings is engaged
    mock_redis.exists.side_effect = Exception("Redis connection lost")
    assert hotpath.is_nonce_used("nonce_test") is True  # present in local _strings
    assert hotpath.is_nonce_used("nonce_nonexistent") is False


def test_live_redis_does_not_leak_keys_into_in_memory_structures():
    """Verifies that under live Redis, operations do NOT store keys in _strings, _ttls, or _hashes."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    mock_redis.eval.return_value = [1, 1, 10]
    mock_redis.hset.return_value = 1

    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)

    # 1. 20,000 nonces
    for i in range(20000):
        hotpath.set_attestation_nonce(f"nonce_{i}", ttl_seconds=10)
    assert len(hotpath._strings) == 0, f"Expected 0 leaked strings, found {len(hotpath._strings)}"
    assert len(hotpath._ttls) == 0, f"Expected 0 leaked ttls, found {len(hotpath._ttls)}"

    # 2. 500 quota increments
    for i in range(500):
        hotpath.check_and_increment_quota(f"0xwallet_{i}", "T1", "202610", 10)
    assert len(hotpath._strings) == 0
    assert len(hotpath._ttls) == 0

    # 3. 500 sun counters
    mock_redis.eval.return_value = 1
    for i in range(500):
        hotpath.check_and_update_sun_counter(f"chip_{i}", 10)
    assert len(hotpath._strings) == 0
    assert len(hotpath._ttls) == 0

    # 4. 500 rate limits
    mock_redis.eval.return_value = [1, 1]
    for i in range(500):
        hotpath.check_rate_limit(f"10.0.0.{i % 250}", max_requests=30)
    assert len(hotpath._strings) == 0
    assert len(hotpath._ttls) == 0

    # 5. 50 paymaster updates and indexer updates
    for i in range(50):
        hotpath.set_paymaster_balance(84532 + i, 1000000000)
        hotpath.update_indexer_head(84532 + i, 1000 + i, "0xhash")
    assert len(hotpath._hashes) == 0


def test_rate_limiting_atomic_redis_execution():
    """Verifies rate limiting executes atomically in Redis via RATE_LIMIT_LUA_SCRIPT."""
    mock_redis = MagicMock()
    # First request: [1 (allowed), 1 (count)]
    mock_redis.eval.return_value = [1, 1]

    hotpath = InMemoryRedisHotPath(redis_client=mock_redis)
    allowed, count = hotpath.check_rate_limit("192.168.1.100", max_requests=2, window_seconds=60)
    assert allowed is True
    assert count == 1
    assert mock_redis.eval.called
    assert mock_redis.eval.call_args[0][0] == RATE_LIMIT_LUA_SCRIPT

    # Rate limit exceeded: [0 (rejected), 2 (count)]
    mock_redis.eval.return_value = [0, 2]
    allowed2, count2 = hotpath.check_rate_limit("192.168.1.100", max_requests=2, window_seconds=60)
    assert allowed2 is False
    assert count2 == 2

    # Redis failure falls back to local memory
    mock_redis.eval.side_effect = Exception("Redis down")
    allowed_fb1, count_fb1 = hotpath.check_rate_limit("10.10.10.10", max_requests=2)
    assert allowed_fb1 is True and count_fb1 == 1
    allowed_fb2, count_fb2 = hotpath.check_rate_limit("10.10.10.10", max_requests=2)
    assert allowed_fb2 is True and count_fb2 == 2
    allowed_fb3, count_fb3 = hotpath.check_rate_limit("10.10.10.10", max_requests=2)
    assert allowed_fb3 is False and count_fb3 == 2


def test_artwork_token_id_allocation_max():
    """Verifies Artwork.token_id allocation uses coalesce(max(Artwork.token_id), 100) + 1."""
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from server.db.models import Base, Artwork

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Empty table -> 101
    max_token = db.query(func.coalesce(func.max(Artwork.token_id), 100)).scalar()
    token_int = int(max_token) + 1
    assert token_int == 101

    # Insert artwork with token_id 101
    art1 = Artwork(
        token_id=101,
        title="Test 1",
        artist_name="Artist",
        artist_wallet="0x1",
        genesis_vector_hash="0xvec",
        chip_id_hash="0xchip",
    )
    db.add(art1)
    db.commit()

    max_token = db.query(func.coalesce(func.max(Artwork.token_id), 100)).scalar()
    token_int = int(max_token) + 1
    assert token_int == 102

    # Non-contiguous token_id (e.g. 150)
    art2 = Artwork(
        token_id=150,
        title="Test 2",
        artist_name="Artist",
        artist_wallet="0x1",
        genesis_vector_hash="0xvec2",
        chip_id_hash="0xchip2",
    )
    db.add(art2)
    db.commit()

    # Even though count is 2, next token must be 151 (not 103)
    assert db.query(Artwork).count() == 2
    max_token = db.query(func.coalesce(func.max(Artwork.token_id), 100)).scalar()
    token_int = int(max_token) + 1
    assert token_int == 151
    db.close()

