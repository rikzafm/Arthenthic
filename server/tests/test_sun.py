import pytest
from server.crypto.sun import SunVerifier

def test_sun_verification_and_anti_replay():
    verifier = SunVerifier(key=b"TestKey128Secret")
    uid = "04010203040506"

    # Counter 1
    cmac1 = verifier.compute_cmac(uid, 1)
    valid, err = verifier.verify_sun(uid, 1, cmac1)
    assert valid is True
    assert err is None

    # Replay Counter 1 -> MUST FAIL
    valid_replay, err_replay = verifier.verify_sun(uid, 1, cmac1)
    assert valid_replay is False
    assert "Replay detected" in err_replay

    # Counter 0 (lower than 1) -> MUST FAIL
    cmac0 = verifier.compute_cmac(uid, 0)
    valid_old, err_old = verifier.verify_sun(uid, 0, cmac0)
    assert valid_old is False
    assert "Replay detected" in err_old

    # Counter 2 (increasing) -> MUST PASS
    cmac2 = verifier.compute_cmac(uid, 2)
    valid2, err2 = verifier.verify_sun(uid, 2, cmac2)
    assert valid2 is True
    assert err2 is None

    # Tampered CMAC -> MUST FAIL
    valid_tamper, err_tamper = verifier.verify_sun(uid, 3, "DEADBEEF12345678")
    assert valid_tamper is False
    assert "Invalid CMAC" in err_tamper

