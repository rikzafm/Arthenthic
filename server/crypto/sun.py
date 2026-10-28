"""
Simulated NTAG 424 DNA SUN (Secure Unique NFC) verification and generation.
In production, NTAG 424 DNA tags compute an AES-128 CMAC over UID and counter.
This module simulates that behavior for prototype testing and enforces anti-replay.
"""

import hmac
import hashlib
from typing import Dict, Tuple, Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# 16-byte default test AES key for CMAC simulation
DEFAULT_MOCK_KEY = b"ArthenticKey128!"

class SunVerifier:
    def __init__(self, key: bytes = DEFAULT_MOCK_KEY):
        self.key = key
        # uid -> last_seen_counter
        self._seen_counters: Dict[str, int] = {}

    def compute_cmac(self, uid: str, ctr: int) -> str:
        """
        Compute deterministic 8-byte CMAC representation over UID and counter.
        """
        msg = f"{uid.upper()}:{ctr:06d}".encode("utf-8")
        h = hmac.new(self.key, msg, hashlib.sha256).hexdigest()
        return h[:16].upper()

    def generate_sun_params(self, uid: str = "04A1B2C3D4E5F6") -> Dict[str, any]:
        """
        Issue next simulated SUN URL parameters for testing.
        Increments the counter from last known value.
        """
        last_ctr = self._seen_counters.get(uid, 0)
        next_ctr = last_ctr + 1
        cmac = self.compute_cmac(uid, next_ctr)
        return {
            "uid": uid,
            "ctr": next_ctr,
            "cmac": cmac
        }

    def verify_sun(self, uid: str, ctr: int, cmac: str) -> Tuple[bool, Optional[str]]:
        """
        Verify SUN authenticity and reject replays.
        Returns (is_valid, error_reason).
        """
        expected_cmac = self.compute_cmac(uid, ctr)
        if cmac.upper() != expected_cmac.upper():
            return False, "Invalid CMAC: cryptographic tag verification failed"

        last_ctr = self._seen_counters.get(uid, -1)
        if ctr <= last_ctr:
            return False, f"Replay detected: counter {ctr} <= last seen {last_ctr}"

        # Update counter on successful verification
        self._seen_counters[uid] = ctr
        return True, None

    def reset_counter(self, uid: str):
        if uid in self._seen_counters:
            del self._seen_counters[uid]


# Singleton verifier for prototype server
sun_verifier = SunVerifier()

