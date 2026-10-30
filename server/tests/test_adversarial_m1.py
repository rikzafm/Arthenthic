"""
server/tests/test_adversarial_m1.py
Empirical Adversarial Challenge Suite for Milestone 1:
1. HSM ASN.1 DER signature conversion, EIP-2 low-s clamping, and recovery byte v in {27, 28}.
2. SIWE wallet authentication bypasses (0xmock, 0xmetamask, debug, empty, impersonation) and replay attacks.
3. OAuth token attacks (alg: none, HS256 key confusion, forged RSA, missing sub, unverified email link).
"""

import os
import json
import secrets
import base64
import hmac
import hashlib
import pytest
import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature, decode_dss_signature
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from server.main import app
from server.node.hsm_signer import (
    HsmProtocolNodeSigner,
    SECP256K1_N,
    SECP256K1_HALF_N,
)
from server.crypto.attestation import TEST_SIGNER_PRIVATE_KEY
from server.auth.oauth import set_jwks_client, reset_jwks_clients, verify_oauth_token
from server.auth.limiter import limiter
from server.auth.clock import get_current_time, reset_clock_provider
from server.storage import store
from server.db.database import SessionLocal, engine, Base
from server.db.models import User

client = TestClient(app)

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


@pytest.fixture(autouse=True)
def clean_environment():
    reset_clock_provider()
    limiter.clear_all()
    yield
    reset_clock_provider()
    limiter.clear_all()


# ==============================================================================
# CHALLENGE 1: HSM ASN.1 DER Signature Conversion & EIP-2 Normalization
# ==============================================================================

class TestHsmSignerAdversarial:
    @pytest.fixture(autouse=True)
    def setup_signer(self):
        self.signer = HsmProtocolNodeSigner(provider="local_enclave")
        self.dev_acct = Account.from_key(TEST_SIGNER_PRIVATE_KEY)

    def test_high_s_signature_clamping_and_evm_compliance(self):
        """
        Adversarial Test: Force high-s signature (s > N // 2) and verify:
        1. DER decoder normalizes s to SECP256K1_N - s (s <= N // 2).
        2. Output signature is standard 65 bytes (132 hex chars with '0x').
        3. Recovered address strictly equals signer's public address.
        """
        digest = secrets.token_bytes(32)
        signed = self.dev_acct.unsafe_sign_hash(digest)
        r, s_low = signed.r, signed.s

        if s_low > SECP256K1_HALF_N:
            s_low = SECP256K1_N - s_low

        s_high = SECP256K1_N - s_low
        assert s_high > SECP256K1_HALF_N, "Engineered s_high must exceed N // 2"

        high_s_der = encode_dss_signature(r, s_high)
        evm_sig = self.signer._der_to_evm_sig(high_s_der, digest)

        assert evm_sig.startswith("0x")
        assert len(evm_sig) == 132, f"EVM signature length must be 132 hex chars, got {len(evm_sig)}"

        sig_bytes = bytes.fromhex(evm_sig[2:])
        extracted_r = int(sig_bytes[:32].hex(), 16)
        extracted_s = int(sig_bytes[32:64].hex(), 16)
        extracted_v = sig_bytes[64]

        assert extracted_s <= SECP256K1_HALF_N, f"High-s was not normalized: s={extracted_s} > {SECP256K1_HALF_N}"
        assert extracted_s == s_low, "Clamped s does not equal expected low-s"
        assert extracted_r == r
        assert extracted_v in (27, 28)

        recovered = Account._recover_hash(digest, vrs=(extracted_v, extracted_r, extracted_s))
        assert recovered.lower() == self.signer.public_address.lower(), (
            f"Recovered address {recovered} does not match signer {self.signer.public_address}"
        )

    def test_recovery_byte_v_coverage_both_27_and_28(self):
        """
        Adversarial Test: Search digests until both v=27 and v=28 recovery bytes
        are produced, verifying that _der_to_evm_sig accurately identifies the
        recovery byte in both cases.
        """
        found_v27 = False
        found_v28 = False

        for _ in range(200):
            if found_v27 and found_v28:
                break
            digest = secrets.token_bytes(32)
            signed = self.dev_acct.unsafe_sign_hash(digest)
            r, s = signed.r, signed.s
            
            der_bytes = encode_dss_signature(r, s)
            evm_sig = self.signer._der_to_evm_sig(der_bytes, digest)
            v = int(evm_sig[-2:], 16)

            assert v in (27, 28), f"Invalid v: {v}"

            rec = Account._recover_hash(digest, vrs=(v, r, s if s <= SECP256K1_HALF_N else SECP256K1_N - s))
            assert rec.lower() == self.signer.public_address.lower()

            if v == 27:
                found_v27 = True
            elif v == 28:
                found_v28 = True

        assert found_v27, "Failed to encounter a v=27 signature in 200 attempts"
        assert found_v28, "Failed to encounter a v=28 signature in 200 attempts"

    def test_randomized_monte_carlo_hsm_high_s_der_stress(self):
        """
        Adversarial Stress Test: 30 random digests signed, forced to high-s,
        converted from DER, and verified for exact address recovery and low-s clamping.
        """
        for _ in range(30):
            digest = secrets.token_bytes(32)
            signed = self.dev_acct.unsafe_sign_hash(digest)
            r = signed.r
            s_low = signed.s if signed.s <= SECP256K1_HALF_N else SECP256K1_N - signed.s
            s_high = SECP256K1_N - s_low

            high_s_der = encode_dss_signature(r, s_high)
            evm_sig = self.signer._der_to_evm_sig(high_s_der, digest)

            s_extracted = int(evm_sig[66:130], 16)
            v_extracted = int(evm_sig[130:132], 16)

            assert s_extracted <= SECP256K1_HALF_N
            assert s_extracted == s_low

            rec = Account._recover_hash(digest, vrs=(v_extracted, r, s_extracted))
            assert rec.lower() == self.signer.public_address.lower()

    def test_malformed_der_rejections(self):
        """
        Adversarial Test: Corrupted, truncated, and empty DER payloads must fail cleanly.
        """
        digest = secrets.token_bytes(32)
        malformed_inputs = [
            b"",
            b"\x30\x00",
            b"\x30\x06\x02\x01\x01\x02\x01",
            b"not_der_at_all",
            secrets.token_bytes(64),
        ]
        for bad_der in malformed_inputs:
            with pytest.raises(Exception):
                self.signer._der_to_evm_sig(bad_der, digest)


# ==============================================================================
# CHALLENGE 2: SIWE Wallet Auth & MetaMask Role Actions
# ==============================================================================

class TestSiweAndMetaMaskAdversarial:
    @pytest.fixture(autouse=True)
    def setup_wallets(self):
        self.alice = Account.create()
        self.bob = Account.create()

    def test_backdoor_bypass_attempts_rejected_in_metamask_auth(self):
        """
        Adversarial Test: Attempt authentication using legacy backdoor values:
        - '0xmock...'
        - '0xmetamask...'
        - 'debug'
        - Empty string
        All MUST return HTTP 401 Unauthorized.
        """
        backdoor_payloads = [
            "0xmock_super_admin_bypass",
            "0xmock1234567890abcdef",
            "0xmetamask_simulated_sig_01",
            "0xmetamask",
            "debug",
            "",
            "0x",
            "short",
        ]

        for bad_sig in backdoor_payloads:
            res_ch = client.post("/v1/auth/metamask/challenge", json={"address": self.alice.address})
            assert res_ch.status_code == 200

            res = client.post(
                "/v1/auth/metamask/login",
                json={"address": self.alice.address, "signature": bad_sig},
            )
            assert res.status_code == 401, f"Bypass succeeded with signature '{bad_sig}': status {res.status_code}"
            assert "INVALID_METAMASK_SIGNATURE" in res.text

    def test_backdoor_bypass_attempts_rejected_in_v1_auth_verify(self):
        """
        Adversarial Test: Attempt verify using legacy backdoor values on /v1/auth/verify:
        All MUST return HTTP 401.
        """
        backdoor_payloads = [
            "0xmock_bypass",
            "0xmetamask_bypass",
            "debug",
            "",
            "0x1234",
        ]

        for bad_sig in backdoor_payloads:
            res_ch = client.post("/v1/auth/challenge", json={"address": self.alice.address})
            assert res_ch.status_code == 200

            res = client.post(
                "/v1/auth/verify",
                json={"address": self.alice.address, "signature": bad_sig},
            )
            assert res.status_code == 401, f"Bypass succeeded on /v1/auth/verify with '{bad_sig}'"

    def test_cross_wallet_impersonation_attack(self):
        """
        Adversarial Test: Bob signs Alice's challenge message.
        Alice's address is submitted with Bob's signature.
        MUST return HTTP 401.
        """
        res_ch = client.post("/v1/auth/metamask/challenge", json={"address": self.alice.address})
        assert res_ch.status_code == 200
        msg = res_ch.json()["message"]

        bob_sig = self.bob.sign_message(encode_defunct(text=msg)).signature.hex()

        res = client.post(
            "/v1/auth/metamask/login",
            json={"address": self.alice.address, "signature": bob_sig},
        )
        assert res.status_code == 401
        assert "INVALID_METAMASK_SIGNATURE" in res.text

        res_ch_v1 = client.post("/v1/auth/challenge", json={"address": self.alice.address})
        v1_msg = res_ch_v1.json()["message"]
        bob_v1_sig = self.bob.sign_message(encode_defunct(text=v1_msg)).signature.hex()

        res_v1 = client.post(
            "/v1/auth/verify",
            json={"address": self.alice.address, "signature": bob_v1_sig},
        )
        assert res_v1.status_code == 401

    def test_nonce_replay_attack_rejected_metamask_auth(self):
        """
        Adversarial Test: Submit valid signature once (succeeds), then immediately
        replay the identical signature a second time.
        Second request MUST be rejected with HTTP 401 due to nonce consumption.
        """
        res_ch = client.post("/v1/auth/metamask/challenge", json={"address": self.alice.address})
        assert res_ch.status_code == 200
        msg = res_ch.json()["message"]

        alice_sig = self.alice.sign_message(encode_defunct(text=msg)).signature.hex()

        # First request: MUST SUCCEED
        res1 = client.post(
            "/v1/auth/metamask/login",
            json={"address": self.alice.address, "signature": alice_sig},
        )
        assert res1.status_code == 200, f"Initial valid auth failed: {res1.text}"

        # Replay request: MUST FAIL
        res2 = client.post(
            "/v1/auth/metamask/login",
            json={"address": self.alice.address, "signature": alice_sig},
        )
        assert res2.status_code == 401, f"Replay attack was NOT rejected! Status: {res2.status_code}"
        assert "INVALID_METAMASK_SIGNATURE" in res2.text

    def test_nonce_replay_attack_rejected_v1_auth_verify(self):
        """
        Adversarial Test: Replay attack against /v1/auth/verify endpoint.
        Second attempt MUST be rejected with HTTP 401.
        """
        res_ch = client.post("/v1/auth/challenge", json={"address": self.alice.address})
        assert res_ch.status_code == 200
        msg = res_ch.json()["message"]

        alice_sig = self.alice.sign_message(encode_defunct(text=msg)).signature.hex()

        # First request: MUST SUCCEED
        res1 = client.post(
            "/v1/auth/verify",
            json={"address": self.alice.address, "signature": alice_sig},
        )
        assert res1.status_code == 200, f"Initial verify failed: {res1.text}"

        # Replay request: MUST FAIL
        res2 = client.post(
            "/v1/auth/verify",
            json={"address": self.alice.address, "signature": alice_sig},
        )
        assert res2.status_code == 401, f"Replay attack was NOT rejected on /v1/auth/verify! Status: {res2.status_code}"

    def test_role_action_adversarial_bypasses(self):
        """
        Adversarial Test: Test /v1/auth/metamask/role-action with:
        1. Backdoor signature ('debug', '0xmock...') -> 400
        2. Signature from wrong address -> 400
        """
        res_ch = client.post("/v1/auth/metamask/challenge", json={"address": self.alice.address})
        alice_sig = self.alice.sign_message(encode_defunct(text=res_ch.json()["message"])).signature.hex()
        res_auth = client.post("/v1/auth/metamask/login", json={"address": self.alice.address, "signature": alice_sig})
        assert res_auth.status_code == 200
        token = res_auth.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Backdoor signature attempt
        res_mock = client.post(
            "/v1/auth/metamask/role-action",
            headers=headers,
            json={
                "action_code": "C-06",
                "address": self.alice.address,
                "signature": "0xmock_action_bypass",
                "token_id": "101",
            },
        )
        assert res_mock.status_code == 400
        assert "INVALID_SIGNATURE" in res_mock.text

        # 2. Bob signs action message for Alice
        action_msg = f"Arthentic Action Authorization\nAction: C-06\nTarget: 101\nActor: {self.alice.address.lower()}"
        bob_sig = self.bob.sign_message(encode_defunct(text=action_msg)).signature.hex()
        res_mismatch = client.post(
            "/v1/auth/metamask/role-action",
            headers=headers,
            json={
                "action_code": "C-06",
                "address": self.alice.address,
                "signature": bob_sig,
                "token_id": "101",
            },
        )
        assert res_mismatch.status_code == 400
        assert "INVALID_SIGNATURE" in res_mismatch.text


# ==============================================================================
# CHALLENGE 3: OAuth Token Verification Attacks (alg: none, HS256, forged RSA)
# ==============================================================================

class TestOAuthAdversarial:
    @pytest.fixture(autouse=True)
    def setup_oauth_jwks(self):
        set_jwks_client("google", MockJWKSClient(TEST_RSA_PUB))
        set_jwks_client("apple", MockJWKSClient(TEST_RSA_PUB))
        yield
        reset_jwks_clients()

    def test_algorithm_none_attack_rejected(self):
        """
        Adversarial Attack: 'none' algorithm JWT.
        Attacker creates an unsigned token claiming sub='attacker_admin' and email='admin@arthentic.io'.
        MUST be rejected with HTTP 401.
        """
        claims = {
            "sub": "attacker_admin_999",
            "email": "admin@arthentic.io",
            "email_verified": True,
            "name": "Admin Attacker",
        }
        none_token = jwt.encode(claims, key=None, algorithm="none")

        with pytest.raises(Exception):
            verify_oauth_token("google", none_token)

        res = client.post(
            "/v1/auth/google",
            json={"id_token": none_token},
        )
        assert res.status_code == 401
        assert "INVALID_OAUTH_TOKEN" in res.text

    def test_hs256_public_key_as_secret_confusion_attack_rejected(self):
        """
        Adversarial Attack: Key Confusion (HMAC with RSA Public Key).
        Attacker extracts the RSA public key PEM bytes, creates an HS256 JWT
        signed using the public key as HMAC secret, hoping the server
        interprets the public key as an HMAC secret.
        MUST be rejected with HTTP 401 because algorithm='RS256' is strictly enforced.
        """
        pub_pem = TEST_RSA_PUB.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        header = {"alg": "HS256", "typ": "JWT"}
        claims = {
            "sub": "confused_admin",
            "email": "admin@arthentic.io",
            "email_verified": True,
            "name": "Confused Admin",
        }
        b64_header = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        b64_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        msg = f"{b64_header}.{b64_payload}".encode()
        sig = base64.urlsafe_b64encode(hmac.new(pub_pem, msg, hashlib.sha256).digest()).decode().rstrip("=")
        hs256_token = f"{b64_header}.{b64_payload}.{sig}"

        with pytest.raises(Exception):
            verify_oauth_token("google", hs256_token)

        res = client.post(
            "/v1/auth/google",
            json={"id_token": hs256_token},
        )
        assert res.status_code == 401
        assert "INVALID_OAUTH_TOKEN" in res.text

    def test_forged_rsa_signature_rejected(self):
        """
        Adversarial Attack: Forged RSA signature using attacker's own RSA key.
        Attacker signs with FORGED_RSA_PRIV, presenting claims for legitimate user.
        MUST be rejected with HTTP 401.
        """
        claims = {
            "sub": "legit_user_sub_123",
            "email": "legit@arthentic.io",
            "email_verified": True,
            "name": "Legit User",
        }
        forged_token = jwt.encode(claims, key=FORGED_RSA_PRIV, algorithm="RS256")

        with pytest.raises(Exception):
            verify_oauth_token("google", forged_token)

        res = client.post(
            "/v1/auth/google",
            json={"id_token": forged_token},
        )
        assert res.status_code == 401
        assert "INVALID_OAUTH_TOKEN" in res.text

    def test_missing_sub_claim_rejected(self):
        """
        Adversarial Attack: Valid RSA signature, but missing 'sub' claim.
        MUST be rejected.
        """
        claims = {
            "email": "nosub@arthentic.io",
            "email_verified": True,
            "name": "No Sub",
        }
        token_no_sub = jwt.encode(claims, key=TEST_RSA_PRIV, algorithm="RS256")

        res = client.post(
            "/v1/auth/google",
            json={"id_token": token_no_sub},
        )
        assert res.status_code == 401
        assert "INVALID_OAUTH_TOKEN" in res.text

    def test_corrupted_signature_rejected(self):
        """
        Adversarial Attack: Valid token with mutated signature bits.
        MUST be rejected.
        """
        claims = {
            "sub": "corrupted_sig_user",
            "email": "user@arthentic.io",
            "email_verified": True,
        }
        token = jwt.encode(claims, key=TEST_RSA_PRIV, algorithm="RS256")
        header, payload, sig = token.split(".")
        corrupted_sig = "A" + sig[1:]
        corrupted_token = f"{header}.{payload}.{corrupted_sig}"

        res = client.post(
            "/v1/auth/google",
            json={"id_token": corrupted_token},
        )
        assert res.status_code == 401
        assert "INVALID_OAUTH_TOKEN" in res.text

    def test_unverified_email_auto_link_attack_rejected(self):
        """
        Adversarial Attack: Pre-existing user with verified email.
        Attacker signs in via OAuth with the same email, but email_verified is False.
        MUST be rejected with HTTP 409 ACCOUNT_LINK_VERIFICATION_REQUIRED.
        """
        db = SessionLocal()
        existing_email = f"target_user_{secrets.token_hex(4)}@arthentic.io"
        now = get_current_time()
        user = User(
            id=str(secrets.token_hex(16)),
            email=existing_email,
            display_name="Target User",
            email_verified_at=now,
            status="active",
            created_at=now,
        )
        db.add(user)
        db.commit()
        db.close()

        claims = {
            "sub": "attacker_oauth_sub",
            "email": existing_email,
            "email_verified": False,
            "name": "Attacker",
        }
        token = jwt.encode(claims, key=TEST_RSA_PRIV, algorithm="RS256")

        res = client.post(
            "/v1/auth/google",
            json={"id_token": token},
        )
        assert res.status_code == 409
        assert "ACCOUNT_LINK_VERIFICATION_REQUIRED" in res.text
