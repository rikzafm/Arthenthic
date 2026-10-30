import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DBSession

from server.main import app
from server.db.database import get_db, SessionLocal, engine, Base
from server.db.models import User, Session, RefreshToken, AuditLog
from server.auth.clock import set_clock_provider, reset_clock_provider
from server.auth.limiter import limiter

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Reset clock and rate limiter before each test
    reset_clock_provider()
    limiter.clear_all()
    # Recreate tables in DB for clean test state
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    reset_clock_provider()
    limiter.clear_all()

def test_signup_success():
    res = client.post("/auth/signup", json={
        "email": "artist@arthentic.io",
        "password": "SecurePassword123!",
        "display_name": "Arthentic Artist",
        "install_id": "test-install-uuid-001",
        "platform": "ios"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "artist@arthentic.io"
    assert data["user"]["display_name"] == "Arthentic Artist"

    # Verify audit log was created
    db = SessionLocal()
    audit = db.query(AuditLog).filter(AuditLog.action == "AUTH_SIGNUP").first()
    assert audit is not None
    assert audit.meta.get("email") == "artist@arthentic.io"
    db.close()

def test_signup_validation_errors():
    # Weak password (< 8 chars)
    res = client.post("/auth/signup", json={
        "email": "user1@test.com",
        "password": "abc"
    })
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "WEAK_PASSWORD"

    # Duplicate email
    res1 = client.post("/auth/signup", json={
        "email": "dup@test.com",
        "password": "Password123!"
    })
    assert res1.status_code == 200

    res2 = client.post("/auth/signup", json={
        "email": "DUP@test.com",
        "password": "Password123!"
    })
    assert res2.status_code == 400
    assert res2.json()["detail"]["error"]["code"] == "EMAIL_TAKEN"

def test_login_and_me():
    # Sign up
    client.post("/auth/signup", json={
        "email": "login_test@arthentic.io",
        "password": "Secret123Password!"
    })

    # Wrong password
    res_wrong = client.post("/auth/login", json={
        "email": "login_test@arthentic.io",
        "password": "WrongPassword999!"
    })
    assert res_wrong.status_code == 401
    assert res_wrong.json()["detail"]["error"]["code"] == "INVALID_CREDENTIALS"

    # Correct login
    res = client.post("/auth/login", json={
        "email": "login_test@arthentic.io",
        "password": "Secret123Password!",
        "install_id": "device-uuid-123"
    })
    assert res.status_code == 200
    data = res.json()
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    # Access /auth/me
    res_me = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["email"] == "login_test@arthentic.io"

def test_refresh_token_rotation():
    # Sign up
    res = client.post("/auth/signup", json={
        "email": "rotation@test.com",
        "password": "Password123!"
    })
    data1 = res.json()
    token1 = data1["refresh_token"]

    # Refresh 1: rotate token1 -> token2
    res_ref1 = client.post("/auth/refresh", json={"refresh_token": token1})
    assert res_ref1.status_code == 200
    data2 = res_ref1.json()
    token2 = data2["refresh_token"]
    assert token2 != token1

    # New access token works
    res_me = client.get("/auth/me", headers={"Authorization": f"Bearer {data2['access_token']}"})
    assert res_me.status_code == 200

    # Refresh 2: rotate token2 -> token3
    res_ref2 = client.post("/auth/refresh", json={"refresh_token": token2})
    assert res_ref2.status_code == 200
    data3 = res_ref2.json()
    token3 = data3["refresh_token"]
    assert token3 != token2

def test_refresh_token_reuse_detection():
    # Sign up
    res = client.post("/auth/signup", json={
        "email": "reuse@test.com",
        "password": "Password123!"
    })
    token1 = res.json()["refresh_token"]

    # Legitimate client rotates token1 -> token2
    res_ref = client.post("/auth/refresh", json={"refresh_token": token1})
    assert res_ref.status_code == 200
    token2 = res_ref.json()["refresh_token"]

    # Attacker replays already-used token1!
    res_replay = client.post("/auth/refresh", json={"refresh_token": token1})
    assert res_replay.status_code == 401
    assert res_replay.json()["detail"]["error"]["code"] == "TOKEN_REUSE_DETECTED"

    # Whole family/session is revoked! Even token2 must now fail:
    res_token2_fail = client.post("/auth/refresh", json={"refresh_token": token2})
    assert res_token2_fail.status_code == 401
    assert res_token2_fail.json()["detail"]["error"]["code"] == "SESSION_REVOKED"

    # Audit log records reuse detection
    db = SessionLocal()
    audit = db.query(AuditLog).filter(AuditLog.action == "AUTH_REUSE_DETECTED").first()
    assert audit is not None
    db.close()

def test_absolute_30_day_expiry():
    # Inject initial clock
    start_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    set_clock_provider(lambda: start_time)

    res = client.post("/auth/signup", json={
        "email": "expiry@test.com",
        "password": "Password123!"
    })
    token = res.json()["refresh_token"]

    # Advance clock by 15 days: refresh should still succeed
    time_day15 = start_time + timedelta(days=15)
    set_clock_provider(lambda: time_day15)

    res_15 = client.post("/auth/refresh", json={"refresh_token": token})
    assert res_15.status_code == 200
    token_15 = res_15.json()["refresh_token"]

    # Advance clock to day 31 (> 30 days absolute cap from login): must fail
    time_day31 = start_time + timedelta(days=31)
    set_clock_provider(lambda: time_day31)

    res_31 = client.post("/auth/refresh", json={"refresh_token": token_15})
    assert res_31.status_code == 401
    assert res_31.json()["detail"]["error"]["code"] == "SESSION_EXPIRED"

def test_rate_limiting():
    # Attempt 5 wrong logins
    for _ in range(5):
        res = client.post("/auth/login", json={
            "email": "brute@test.com",
            "password": "WrongPassword1!"
        })
        assert res.status_code == 401

    # 6th attempt should be rate limited
    res_limited = client.post("/auth/login", json={
        "email": "brute@test.com",
        "password": "WrongPassword1!"
    })
    assert res_limited.status_code == 429
    assert res_limited.json()["detail"]["error"]["code"] == "RATE_LIMIT_EXCEEDED"

def test_logout():
    res = client.post("/auth/signup", json={
        "email": "logout@test.com",
        "password": "Password123!"
    })
    access_token = res.json()["access_token"]
    refresh_token = res.json()["refresh_token"]

    # Logout
    res_logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {access_token}"})
    assert res_logout.status_code == 200
    assert res_logout.json()["status"] == "ok"

    # Accessing /auth/me after logout must fail
    res_me = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert res_me.status_code == 401
    assert res_me.json()["detail"]["error"]["code"] == "SESSION_REVOKED"

    # Refreshing after logout must fail
    res_ref = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert res_ref.status_code == 401
    assert res_ref.json()["detail"]["error"]["code"] == "SESSION_REVOKED"

