import uuid
import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.db.database import get_db, Base, engine
from server.db.models import User, Session, RefreshToken, ActionToken, AuditLog
from server.auth.clock import set_clock_provider, reset_clock_provider
from server.auth.limiter import limiter

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_clock():
    reset_clock_provider()
    limiter.clear_all()
    yield
    reset_clock_provider()
    limiter.clear_all()

def create_unique_user():
    email = f"user_{uuid.uuid4().hex[:8]}@arthentic.io"
    password = "StrongPassword123!"
    res = client.post("/auth/signup", json={
        "email": email,
        "password": password,
        "display_name": "Test User",
        "device_name": "iPhone 15 Pro",
        "platform": "ios",
        "install_id": f"inst_{uuid.uuid4().hex[:8]}",
    })
    assert res.status_code == 200
    data = res.json()
    return email, password, data["access_token"], data["refresh_token"], data["user"]

def test_session_list_and_remote_revoke():
    email, password, access1, refresh1, user = create_unique_user()

    # Create a second session for the same user (e.g. on an iPad)
    res2 = client.post("/auth/login", json={
        "email": email,
        "password": password,
        "device_name": "iPad Pro",
        "platform": "ios",
        "install_id": f"inst_ipad_{uuid.uuid4().hex[:8]}",
    })
    assert res2.status_code == 200
    data2 = res2.json()
    access2 = data2["access_token"]
    refresh2 = data2["refresh_token"]

    # 1. List sessions from device 1
    list_res = client.get("/v1/auth/sessions", headers={"Authorization": f"Bearer {access1}"})
    assert list_res.status_code == 200
    sessions = list_res.json()["sessions"]
    assert len(sessions) >= 2

    current_sess = next((s for s in sessions if s["is_current"]), None)
    other_sess = next((s for s in sessions if not s["is_current"]), None)
    assert current_sess is not None
    assert other_sess is not None

    # 2. Remote revoke the other session (iPad)
    revoke_res = client.post(
        f"/v1/auth/sessions/{other_sess['id']}/revoke",
        headers={"Authorization": f"Bearer {access1}"},
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "ok"

    # 3. Refreshing token with revoked session fails
    ref_fail = client.post("/auth/refresh", json={"refresh_token": refresh2})
    assert ref_fail.status_code == 401
    assert "SESSION_REVOKED" in ref_fail.json()["detail"]["error"]["code"]

    # 4. Device 1 session still valid
    ref_ok = client.post("/auth/refresh", json={"refresh_token": refresh1})
    assert ref_ok.status_code == 200

def test_change_password_flow():
    email, password, access, refresh, user = create_unique_user()

    # 1. Invalid current password fails
    fail_res = client.post(
        "/v1/auth/password/change",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": "WrongPassword999!", "new_password": "BrandNewPass999!"},
    )
    assert fail_res.status_code == 400
    assert fail_res.json()["detail"]["error"]["code"] == "INVALID_CURRENT_PASSWORD"

    # 2. Weak new password fails
    weak_res = client.post(
        "/v1/auth/password/change",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": password, "new_password": "weak"},
    )
    assert weak_res.status_code == 400
    assert weak_res.json()["detail"]["error"]["code"] == "WEAK_PASSWORD"

    # 3. Successful change
    new_password = "BrandNewPass999!"
    change_res = client.post(
        "/v1/auth/password/change",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": password, "new_password": new_password},
    )
    assert change_res.status_code == 200
    assert change_res.json()["status"] == "ok"

    # 4. Old password login rejected
    old_login = client.post("/auth/login", json={"email": email, "password": password})
    assert old_login.status_code == 401

    # 5. New password login succeeds
    new_login = client.post("/auth/login", json={"email": email, "password": new_password})
    assert new_login.status_code == 200

def test_forgot_and_reset_password_flow():
    email, password, access, refresh, user = create_unique_user()

    # 1. Forgot password with non-existent email returns generic ok (no email enumeration)
    non_exist = client.post("/v1/auth/password/forgot", json={"email": "nobody_exists@arthentic.io"})
    assert non_exist.status_code == 200
    assert "reset_token" not in non_exist.json()

    # 2. Forgot password for real user returns reset token
    forgot_res = client.post("/v1/auth/password/forgot", json={"email": email})
    assert forgot_res.status_code == 200
    reset_token = forgot_res.json().get("reset_token")
    assert reset_token is not None

    # 3. Weak password rejection on reset
    weak_reset = client.post("/v1/auth/password/reset", json={
        "token": reset_token,
        "new_password": "short",
    })
    assert weak_reset.status_code == 400
    assert weak_reset.json()["detail"]["error"]["code"] == "WEAK_PASSWORD"

    # 4. Successful password reset
    reset_pass = "ResetNewSecurePassword888!"
    reset_res = client.post("/v1/auth/password/reset", json={
        "token": reset_token,
        "new_password": reset_pass,
    })
    assert reset_res.status_code == 200

    # 5. Token reuse rejected
    reuse_res = client.post("/v1/auth/password/reset", json={
        "token": reset_token,
        "new_password": reset_pass,
    })
    assert reuse_res.status_code == 400
    assert reuse_res.json()["detail"]["error"]["code"] == "INVALID_RESET_TOKEN"

    # 6. Login with new password works
    login_res = client.post("/auth/login", json={"email": email, "password": reset_pass})
    assert login_res.status_code == 200

def test_email_verification_flow():
    email, password, access, refresh, user = create_unique_user()

    # 1. Request verification
    req_res = client.post(
        "/v1/auth/verify-email/request",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert req_res.status_code == 200
    verify_token = req_res.json().get("verify_token")
    assert verify_token is not None

    # 2. Confirm verification
    confirm_res = client.post("/v1/auth/verify-email/confirm", json={"token": verify_token})
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "ok"

    # 3. Token cannot be reused
    reuse_res = client.post("/v1/auth/verify-email/confirm", json={"token": verify_token})
    assert reuse_res.status_code == 400
    assert reuse_res.json()["detail"]["error"]["code"] == "INVALID_VERIFY_TOKEN"

def test_delete_account_and_audit():
    email, password, access, refresh, user = create_unique_user()

    # 1. User views security audit events
    audit_res = client.get("/v1/auth/audit-log", headers={"Authorization": f"Bearer {access}"})
    assert audit_res.status_code == 200
    assert len(audit_res.json()["events"]) >= 1

    # 2. Delete account (Apple App Store Guideline 5.1.1(v))
    del_res = client.delete("/v1/auth/account", headers={"Authorization": f"Bearer {access}"})
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "ok"

    # 3. Subsequent refresh with session fails
    ref_res = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert ref_res.status_code == 401

    # 4. Subsequent login with email/password fails
    log_res = client.post("/auth/login", json={"email": email, "password": password})
    assert log_res.status_code == 401

def test_password_reset_rate_limiting_and_expiration():
    email, password, access, refresh, user = create_unique_user()

    # 1. First request returns reset token
    res1 = client.post("/v1/auth/password/forgot", json={"email": email})
    assert res1.status_code == 200
    token1 = res1.json().get("reset_token")

    # 2. Fire 4 more requests (total 5)
    for _ in range(4):
        res = client.post("/v1/auth/password/forgot", json={"email": email})
        assert res.status_code == 200

    # 3. 6th request trips rate limiting (HTTP 429)
    res_rate_limited = client.post("/v1/auth/password/forgot", json={"email": email})
    assert res_rate_limited.status_code == 429
    assert res_rate_limited.json()["detail"]["error"]["code"] == "RATE_LIMITED"

    # 4. Advance clock by 2 hours (token expires after 1 hour)
    from datetime import datetime, timezone, timedelta
    from server.auth.clock import get_current_time
    now = get_current_time()
    set_clock_provider(lambda: now + timedelta(hours=2))

    res_expired = client.post("/v1/auth/password/reset", json={
        "token": token1,
        "new_password": "AnotherStrongPassword999!",
    })
    assert res_expired.status_code == 400
    assert res_expired.json()["detail"]["error"]["code"] == "EXPIRED_RESET_TOKEN"

def test_email_verify_rate_limiting_and_expiration():
    email, password, access, refresh, user = create_unique_user()

    # 1. Request verification token
    res1 = client.post("/v1/auth/verify-email/request", headers={"Authorization": f"Bearer {access}"})
    assert res1.status_code == 200
    vtoken = res1.json().get("verify_token")

    # 2. Fire 4 more requests
    for _ in range(4):
        res = client.post("/v1/auth/verify-email/request", headers={"Authorization": f"Bearer {access}"})
        assert res.status_code == 200

    # 3. 6th request trips rate limiting
    res_rl = client.post("/v1/auth/verify-email/request", headers={"Authorization": f"Bearer {access}"})
    assert res_rl.status_code == 429
    assert res_rl.json()["detail"]["error"]["code"] == "RATE_LIMITED"

    # 4. Advance clock by 25 hours (email verify token expires after 24 hours)
    from datetime import datetime, timezone, timedelta
    from server.auth.clock import get_current_time
    now = get_current_time()
    set_clock_provider(lambda: now + timedelta(hours=25))

    res_exp = client.post("/v1/auth/verify-email/confirm", json={"token": vtoken})
    assert res_exp.status_code == 400
    assert res_exp.json()["detail"]["error"]["code"] == "EXPIRED_VERIFY_TOKEN"

def test_account_deletion_pii_scrubbing_and_anonymization():
    email, password, access, refresh, user_info = create_unique_user()
    user_id = user_info["id"]

    # Delete account
    del_res = client.delete("/v1/auth/account", headers={"Authorization": f"Bearer {access}"})
    assert del_res.status_code == 200

    # Query DB directly to verify complete PII anonymization
    from server.db.database import SessionLocal
    db = SessionLocal()
    try:
        user_row = db.query(User).filter(User.id == user_id).first()
        assert user_row is not None
        assert user_row.status == "deleted"
        assert user_row.email.startswith("deleted_")
        assert user_row.email.endswith("@deleted.arthentic.io")
        assert user_row.display_name == "Deleted Account"
        assert user_row.password_hash is None

        # Verify all sessions revoked
        sessions = db.query(Session).filter(Session.user_id == user_id).all()
        assert len(sessions) > 0
        for s in sessions:
            assert s.revoked_at is not None
            assert s.revoke_reason == "ACCOUNT_DELETED"
    finally:
        db.close()

