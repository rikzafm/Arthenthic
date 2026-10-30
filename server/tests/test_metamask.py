import pytest
import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from server.main import app
from server.db.database import SessionLocal, engine, Base
from server.db.models import WalletLink, AuditLog
from server.auth.service import grant_user_role
from server.auth.clock import reset_clock_provider
from server.auth.limiter import limiter
from server.auth.oauth import set_jwks_client, reset_jwks_clients

client = TestClient(app)

TEST_RSA_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_RSA_PUB = TEST_RSA_PRIV.public_key()


class MockSigningKey:
    def __init__(self, key):
        self.key = key


class MockJWKSClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str):
        return MockSigningKey(self.public_key)


def make_oauth_jwt(sub: str, email: str, name: str = "Test User") -> str:
    claims = {"sub": sub, "email": email, "email_verified": True, "name": name}
    return jwt.encode(claims, TEST_RSA_PRIV, algorithm="RS256", headers={"kid": "test-kid"})


def sign_role_action(account, action_code: str, token_id: str = "101") -> str:
    canonical_msg = (
        f"Arthentic Action Authorization\n"
        f"Action: {action_code}\n"
        f"Target: {token_id}\n"
        f"Actor: {account.address.lower()}"
    )
    signed = account.sign_message(encode_defunct(text=canonical_msg))
    return "0x" + signed.signature.hex()


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


def test_metamask_challenge_and_real_ecdsa_login():
    acct = Account.create("arthentic-metamask-test-entropy")
    address = acct.address

    # 1. Request SIWE challenge
    ch_res = client.post("/v1/auth/metamask/challenge", json={"address": address, "chain_id": 84532})
    assert ch_res.status_code == 200
    ch_data = ch_res.json()
    assert ch_data["address"] == address.lower()
    assert "nonce" in ch_data
    assert "wc_deep_link" in ch_data

    # 2. Sign challenge message with real ECDSA private key (as MetaMask does)
    msg = encode_defunct(text=ch_data["message"])
    signed = acct.sign_message(msg)
    sig_hex = "0x" + signed.signature.hex()

    # 3. Log in with MetaMask signature
    login_res = client.post(
        "/v1/auth/metamask/login",
        json={
            "address": address,
            "signature": sig_hex,
            "chain_id": 84532,
            "wallet_type": "metamask",
            "install_id": "ios_metamask_01",
        },
    )
    assert login_res.status_code == 200, login_res.text
    data = login_res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["wallet_address"] == address.lower()
    assert "Collector" in data["user"]["roles"]
    assert len(data["user"]["wallets"]) == 1

    # Verify DB WalletLink record
    db = SessionLocal()
    wl = db.query(WalletLink).filter(WalletLink.address == address.lower()).first()
    assert wl is not None
    assert wl.wallet_type == "metamask"
    assert wl.chain_id == 84532
    assert wl.is_primary is True
    db.close()


def test_link_metamask_to_google_account():
    # 1. Sign in with Google first using genuine RS256 token
    google_token = make_oauth_jwt("g_sub_99", "collector.google@arthentic.io", "Collector Google")
    g_res = client.post("/auth/google", json={"id_token": google_token})
    assert g_res.status_code == 200
    access_token = g_res.json()["access_token"]
    user_id = g_res.json()["user"]["id"]

    # 2. Link MetaMask wallet to this Google account using genuine signed challenge
    mm_acct = Account.create()
    mm_addr = mm_acct.address
    ch_res = client.post("/v1/auth/metamask/challenge", json={"address": mm_addr})
    assert ch_res.status_code == 200
    sig_link = "0x" + mm_acct.sign_message(encode_defunct(text=ch_res.json()["message"])).signature.hex()

    link_res = client.post(
        "/v1/auth/metamask/link",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "address": mm_addr,
            "signature": sig_link,
            "chain_id": 84532,
            "label": "MetaMask Mobile (iPhone)",
        },
    )
    assert link_res.status_code == 200, link_res.text
    assert link_res.json()["status"] == "linked"
    assert link_res.json()["wallet"]["address"] == mm_addr.lower()

    # 3. Subsequent MetaMask login resolves to the SAME Google-linked user account!
    ch_res2 = client.post("/v1/auth/metamask/challenge", json={"address": mm_addr})
    assert ch_res2.status_code == 200
    sig_login = "0x" + mm_acct.sign_message(encode_defunct(text=ch_res2.json()["message"])).signature.hex()

    mm_login = client.post(
        "/v1/auth/metamask/login",
        json={"address": mm_addr, "signature": sig_login},
    )
    assert mm_login.status_code == 200
    assert mm_login.json()["user"]["id"] == user_id
    assert mm_login.json()["user"]["email"] == "collector.google@arthentic.io"


def test_metamask_role_actions_and_rbac_enforcement():
    role_acct = Account.create()
    mm_addr = role_acct.address

    ch_res = client.post("/v1/auth/metamask/challenge", json={"address": mm_addr})
    assert ch_res.status_code == 200
    sig_login = "0x" + role_acct.sign_message(encode_defunct(text=ch_res.json()["message"])).signature.hex()

    login_res = client.post(
        "/v1/auth/metamask/login",
        json={"address": mm_addr, "signature": sig_login},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    user_id = login_res.json()["user"]["id"]

    # 1. Collector can execute C-06 Tap Claim via MetaMask with genuine signature
    sig_c06 = sign_role_action(role_acct, "C-06", "101")
    c06_res = client.post(
        "/v1/auth/metamask/role-action",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_code": "C-06",
            "address": mm_addr,
            "signature": sig_c06,
            "token_id": "101",
            "payload": {"listingId": 1, "sunCounter": 42},
        },
    )
    assert c06_res.status_code == 200
    assert c06_res.json()["action_code"] == "C-06"
    assert c06_res.json()["status"] == "CONFIRMED"

    # 2. Collector attempting B-07 (Artist Genesis Co-Signature) without Artist role -> 403 Forbidden
    sig_b07 = sign_role_action(role_acct, "B-07", "101")
    b07_forbidden = client.post(
        "/v1/auth/metamask/role-action",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_code": "B-07",
            "address": mm_addr,
            "signature": sig_b07,
            "token_id": "101",
        },
    )
    assert b07_forbidden.status_code == 403
    assert b07_forbidden.json()["detail"]["error"]["code"] == "ROLE_REQUIRED_FOR_METAMASK_ACTION"

    # 3. Grant Artist and Conservator roles to user and verify B-07 and E-03 succeed
    db = SessionLocal()
    grant_user_role(db, user_id=user_id, role="Artist")
    grant_user_role(db, user_id=user_id, role="Conservator")
    db.close()

    b07_ok = client.post(
        "/v1/auth/metamask/role-action",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_code": "B-07",
            "address": mm_addr,
            "signature": sig_b07,
            "token_id": "101",
        },
    )
    assert b07_ok.status_code == 200
    assert b07_ok.json()["role"] == "Artist"

    sig_e03 = sign_role_action(role_acct, "E-03", "101")
    e03_ok = client.post(
        "/v1/auth/metamask/role-action",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_code": "E-03",
            "address": mm_addr,
            "signature": sig_e03,
            "token_id": "101",
            "payload": {"newVectorHash": "0xabc123", "noteURI": "ar://restoration_report_1"},
        },
    )
    assert e03_ok.status_code == 200
    assert e03_ok.json()["role"] == "Conservator"

    # 4. Forged signature from different account -> 400 Bad Request
    other_acct = Account.create()
    forged_sig = sign_role_action(other_acct, "C-06", "101")
    forged_res = client.post(
        "/v1/auth/metamask/role-action",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_code": "C-06",
            "address": mm_addr,
            "signature": forged_sig,
            "token_id": "101",
        },
    )
    assert forged_res.status_code == 400
    assert forged_res.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_metamask_mock_and_debug_bypasses_rejected():
    acct = Account.create()
    # 1. Mock prefix signature rejected
    res1 = client.post(
        "/v1/auth/metamask/login",
        json={"address": acct.address, "signature": "0xmetamask_simulated_sig_01"},
    )
    assert res1.status_code == 401

    # 2. 0xmock prefix signature rejected
    res2 = client.post(
        "/v1/auth/metamask/login",
        json={"address": acct.address, "signature": "0xmock_admin_bypass"},
    )
    assert res2.status_code == 401

    # 3. debug signature rejected
    res3 = client.post(
        "/v1/auth/metamask/login",
        json={"address": acct.address, "signature": "debug"},
    )
    assert res3.status_code == 401
