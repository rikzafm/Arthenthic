import pytest
import jwt
from fastapi.testclient import TestClient
from server.main import app
from server.config import settings
from server.auth.tokens import create_access_token, decode_access_token
from server.auth.monitoring import monitoring
from server.db.seed import seed_dev_users

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_seed():
    seed_dev_users()
    yield

@pytest.fixture(autouse=True)
def reset_monitoring():
    orig_kid = settings.JWT_ACTIVE_KID
    orig_keys = dict(settings._jwt_keys)
    monitoring.reset()
    yield
    monitoring.reset()
    settings._jwt_keys = orig_keys
    settings.JWT_ACTIVE_KID = orig_kid

class TestTokenKeyRotationM7:
    """
    Milestone 7: Token signing-key rotation runbook and multi-key verification testing.
    Verifies support for 'kid' header and dual-key zero-downtime rotation.
    """

    def test_kid_header_included_in_access_tokens(self):
        token = create_access_token(user_id="user_123", session_id="sess_123", roles=["Artist"])
        header = jwt.get_unverified_header(token)
        assert "kid" in header
        assert header["kid"] == settings.JWT_ACTIVE_KID

        decoded = decode_access_token(token)
        assert decoded["sub"] == "user_123"
        assert decoded["roles"] == ["Artist"]

    def test_zero_downtime_dual_key_rotation(self):
        # 1. Sign a token with Key 1 ("v1")
        settings.register_key("v1", "secret-key-1-at-least-32-characters-long!", make_active=True)
        token_v1 = create_access_token(user_id="usr_v1", session_id="sess_v1")

        # 2. Rotate to Key 2 ("v2") while retaining Key 1 in registry
        settings.register_key("v2", "secret-key-2-at-least-32-characters-long!", make_active=True)
        assert settings.JWT_ACTIVE_KID == "v2"

        # 3. New tokens are signed with Key 2 ("v2")
        token_v2 = create_access_token(user_id="usr_v2", session_id="sess_v2")
        header_v2 = jwt.get_unverified_header(token_v2)
        assert header_v2["kid"] == "v2"

        # 4. Both tokens verify seamlessly!
        decoded_v1 = decode_access_token(token_v1)
        assert decoded_v1["sub"] == "usr_v1"

        decoded_v2 = decode_access_token(token_v2)
        assert decoded_v2["sub"] == "usr_v2"

    def test_unknown_kid_rejected(self):
        # Sign token with an unregistered kid
        payload = {"sub": "rogue", "sid": "rogue_sid"}
        rogue_token = jwt.encode(payload, "secret-32-chars-long-something-else!", algorithm="HS256", headers={"kid": "unknown_kid_99"})
        with pytest.raises(jwt.InvalidTokenError, match="unknown key id"):
            decode_access_token(rogue_token)

class TestMonitoringAndMetricsM7:
    """
    Milestone 7: Monitoring endpoints (auth failure rates, refresh failures, lock-bypass reports).
    """

    def test_monitoring_records_login_and_refresh_metrics(self):
        # 1. Record mock security events
        monitoring.record_login_success()
        monitoring.record_login_success()
        monitoring.record_login_failure("invalid_password")
        monitoring.record_refresh_success()
        monitoring.record_refresh_failure("expired")
        monitoring.record_token_reuse("user_suspect_456")
        monitoring.record_lock_bypass(details="Face ID prompt aborted repeatedly")

        stats = monitoring.get_stats()
        assert stats["auth"]["login_successes"] == 2
        assert stats["auth"]["login_failures"] == 1
        assert stats["auth"]["total_logins"] == 3
        assert stats["auth"]["login_failure_rate"] == pytest.approx(0.3333, abs=0.01)

        assert stats["tokens"]["refresh_successes"] == 1
        assert stats["tokens"]["refresh_failures"] == 1
        assert stats["tokens"]["token_reuse_events"] == 1

        assert stats["security"]["lock_bypass_reports"] == 1
        assert stats["status"] == "ALERT"

    def test_prometheus_metrics_endpoint(self):
        monitoring.record_login_success()
        monitoring.record_token_reuse("user_theft")

        res = client.get("/metrics")
        assert res.status_code == 200
        text = res.text
        assert "auth_login_successes_total 1" in text
        assert "auth_token_reuse_events_total 1" in text
        assert "app_lock_bypass_reports_total 0" in text

    def test_admin_monitoring_stats_endpoint(self):
        # Admin logs in to query /v1/admin/monitoring/stats
        admin_login = client.post("/auth/login", json={"email": "admin@arthentic.io", "password": "Admin123!"})
        assert admin_login.status_code == 200
        admin_token = admin_login.json()["access_token"]

        stats_res = client.get("/v1/admin/monitoring/stats", headers={"Authorization": f"Bearer {admin_token}"})
        assert stats_res.status_code == 200
        data = stats_res.json()
        assert "auth" in data
        assert "tokens" in data
        assert "security" in data

    def test_lock_bypass_reporting_endpoint(self):
        res = client.post("/v1/auth/lock-bypass-report", json={
            "details": "Biometrics failed 5 times; passcode fallback was skipped by user",
        })
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        stats = monitoring.get_stats()
        assert stats["security"]["lock_bypass_reports"] >= 1
