import pytest
import jwt
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from server.main import app
from server.db.database import get_db, SessionLocal, engine, Base
from server.db.models import User, AuthIdentity, AuditLog
from server.auth.clock import set_clock_provider, reset_clock_provider
from server.auth.oauth import set_jwks_client, reset_jwks_clients
from server.auth.limiter import limiter

client = TestClient(app)

# Local test RSA 2048 key pairs
TEST_RSA_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_RSA_PUB = TEST_RSA_PRIV.public_key()

FORGED_RSA_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class MockSigningKey:
    def __init__(self, key):
        self.key = key


class MockJWKSClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str):
        return MockSigningKey(self.public_key)


def make_oauth_jwt(
    sub: str,
    email: str,
    name: str = "Test User",
    email_verified: bool = True,
    private_key=TEST_RSA_PRIV,
    kid: str = "test-key-id",
) -> str:
    claims = {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "name": name,
    }
    headers = {"kid": kid}
    return jwt.encode(claims, private_key, algorithm="RS256", headers=headers)


@pytest.fixture(autouse=True)
def setup_and_teardown():
    reset_clock_provider()
    limiter.clear_all()
    mock_jwks = MockJWKSClient(TEST_RSA_PUB)
    set_jwks_client("google", mock_jwks)
    set_jwks_client("apple", mock_jwks)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    reset_clock_provider()
    limiter.clear_all()
    reset_jwks_clients()


def test_new_google_user_creation():
    token = make_oauth_jwt(
        sub="google_sub_1001",
        email="google.artist@arthentic.io",
        name="Google Artist",
    )

    res = client.post("/auth/google", json={"id_token": token, "install_id": "device_001"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "google.artist@arthentic.io"
    assert data["user"]["display_name"] == "Google Artist"

    # Verify DB records
    db = SessionLocal()
    identity = db.query(AuthIdentity).filter(AuthIdentity.provider_subject == "google_sub_1001").first()
    assert identity is not None
    assert identity.provider == "google"
    user = db.query(User).filter(User.id == identity.user_id).first()
    assert user is not None
    assert user.password_hash is None  # Google-only user
    assert user.email_verified_at is not None

    audit = db.query(AuditLog).filter(AuditLog.action == "AUTH_GOOGLE_SIGNUP").first()
    assert audit is not None
    db.close()


def test_returning_google_user_login():
    token = make_oauth_jwt(
        sub="google_sub_1002",
        email="returning@arthentic.io",
        name="Returning Artist",
    )

    # First sign up
    res1 = client.post("/auth/google", json={"id_token": token})
    assert res1.status_code == 200
    user_id_1 = res1.json()["user"]["id"]

    # Second login
    res2 = client.post("/auth/google", json={"id_token": token})
    assert res2.status_code == 200
    assert res2.json()["user"]["id"] == user_id_1

    db = SessionLocal()
    identities_count = db.query(AuthIdentity).filter(AuthIdentity.provider_subject == "google_sub_1002").count()
    assert identities_count == 1
    db.close()


def test_auto_link_to_existing_verified_account():
    # 1. Create existing user with verified email
    db = SessionLocal()
    user = User(
        id="existing_verified_user_id",
        email="shared@arthentic.io",
        display_name="Existing Verified User",
        password_hash="somehash",
        email_verified_at=datetime.now(timezone.utc),
        status="active",
    )
    db.add(user)
    db.commit()
    db.close()

    # 2. Sign in with Google using matching verified email signed with genuine RS256
    token = make_oauth_jwt(
        sub="google_sub_2001",
        email="shared@arthentic.io",
        name="Shared User",
    )
    res = client.post("/auth/google", json={"id_token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["id"] == "existing_verified_user_id"

    # Verify identity linked to existing user
    db = SessionLocal()
    identity = db.query(AuthIdentity).filter(AuthIdentity.provider_subject == "google_sub_2001").first()
    assert identity is not None
    assert identity.user_id == "existing_verified_user_id"
    db.close()


def test_auto_link_blocked_if_existing_account_not_verified():
    # 1. Existing user has NOT verified email
    db = SessionLocal()
    user = User(
        id="existing_unverified_user_id",
        email="unverified@arthentic.io",
        display_name="Unverified User",
        password_hash="somehash",
        email_verified_at=None,  # Not verified!
        status="active",
    )
    db.add(user)
    db.commit()
    db.close()

    # 2. Attack attempt: attacker tries to take over the account via OAuth match
    token = make_oauth_jwt(
        sub="google_sub_3001",
        email="unverified@arthentic.io",
        name="Attacker",
    )
    res = client.post("/auth/google", json={"id_token": token})
    assert res.status_code == 409
    assert res.json()["detail"]["error"]["code"] == "ACCOUNT_LINK_VERIFICATION_REQUIRED"


def test_apple_sign_in():
    token = make_oauth_jwt(
        sub="apple_sub_9999",
        email="collector@privaterelay.appleid.com",
        name="Apple Collector",
    )
    res = client.post("/auth/apple", json={"id_token": token, "platform": "ios"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "collector@privaterelay.appleid.com"

    db = SessionLocal()
    identity = db.query(AuthIdentity).filter(AuthIdentity.provider == "apple").first()
    assert identity is not None
    assert identity.provider_subject == "apple_sub_9999"
    db.close()


def test_authenticated_user_link_provider():
    # 1. Sign up with email/password
    signup_res = client.post("/auth/signup", json={
        "email": "password.user@arthentic.io",
        "password": "Password123!"
    })
    access_token = signup_res.json()["access_token"]
    user_id = signup_res.json()["user"]["id"]

    # 2. Link Google account from settings
    google_token = make_oauth_jwt(
        sub="google_sub_linked_1",
        email="password.user@arthentic.io",
        name="Password User",
    )
    link_res = client.post(
        "/auth/link",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"provider": "google", "id_token": google_token}
    )
    assert link_res.status_code == 200
    assert link_res.json()["status"] == "ok"

    # 3. Verify in DB
    db = SessionLocal()
    identity = db.query(AuthIdentity).filter(AuthIdentity.user_id == user_id).first()
    assert identity is not None
    assert identity.provider == "google"
    assert identity.provider_subject == "google_sub_linked_1"
    db.close()

    # 4. Now the user can log in directly with Google!
    login_res = client.post("/auth/google", json={"id_token": google_token})
    assert login_res.status_code == 200
    assert login_res.json()["user"]["id"] == user_id


def test_forged_oauth_token_rejected():
    # Token signed with an untrusted / forged RSA private key must be rejected
    forged_token = make_oauth_jwt(
        sub="forged_attacker_sub",
        email="attacker@arthentic.io",
        private_key=FORGED_RSA_PRIV,
    )
    res = client.post("/auth/google", json={"id_token": forged_token})
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_OAUTH_TOKEN"


def test_mock_prefix_bypass_rejected():
    # Token using the legacy 'mock_' prefix string must be rejected
    res = client.post(
        "/auth/google",
        json={"id_token": "mock_google:evil:admin@arthentic.io:1:Admin"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_OAUTH_TOKEN"
