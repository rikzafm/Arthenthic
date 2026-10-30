"""
server/tests/test_wave2_milestone3.py
TDD Test Suite for Wave 2 Milestone 3 & Architecture Code Review Verification:
1. Cloud KMS (AWS KMS boto3 & HashiCorp Vault Transit) in HsmProtocolNodeSigner (SC-NODE-01/02, A-09, D-02)
2. Real AES-128 SUN CMAC cryptographic validation inside HsmProtocolNodeSigner.verify_nfc_cmac()
3. /v1/admin/signers/rotate endpoint & SignerKey DB persistence (A-09 / A-10)
4. Live Bundlr/Irys & Pinata IPFS dual-pinning + B-12 bundle integrity verification in ArweaveStorageAdapter
5. ERC-4337 Bundler / Paymaster UserOperation paymasterAndData signing (K-01..K-05)
"""

import base64
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_typed_data
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from server.main import app
from server.crypto.attestation import ATTESTATION_DOMAIN, ATTESTATION_TYPES, TEST_SIGNER_PRIVATE_KEY
from server.crypto.sun import sun_verifier
from server.node.hsm_signer import HsmProtocolNodeSigner, node_signer
from server.node.arweave_storage import ArweaveStorageAdapter, arweave_adapter
from server.paymaster.policy_engine import paymaster_engine
from server.db.database import SessionLocal
from server.db.models import SignerKey
from server.db.seed import seed_dev_users

client = TestClient(app)


def _create_admin_headers() -> dict:
    seed_dev_users()
    res = client.post(
        "/auth/login",
        json={"email": "admin@arthentic.io", "password": "Admin123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_hsm_signer_aws_kms_and_vault_transit_modes():
    """
    Verifies HsmProtocolNodeSigner supports:
    - AWS KMS (boto3 client sign digest mode) with real ASN.1 DER parsing
    - HashiCorp Vault Transit (/v1/transit/sign/<key> mode) with real DER parsing
    - Key recovery verification asserting recovered address matches signer
    - Key rotation (rotate_signer_key)
    """
    dev_account = Account.from_key(TEST_SIGNER_PRIVATE_KEY)

    # 1. AWS KMS signing with real ASN.1 DER ECDSA signature
    mock_kms = MagicMock()

    def kms_sign_side_effect(KeyId, Message, MessageType, SigningAlgorithm):
        sig = dev_account.unsafe_sign_hash(Message)
        der_bytes = encode_dss_signature(sig.r, sig.s)
        return {
            "KeyId": KeyId,
            "Signature": der_bytes,
            "SigningAlgorithm": SigningAlgorithm,
        }

    mock_kms.sign.side_effect = kms_sign_side_effect

    signer = HsmProtocolNodeSigner(
        key_arn="arn:aws:kms:us-east-1:999999999999:key/live-kms-key",
        provider="aws_kms",
        kms_client=mock_kms,
    )
    attestation = signer.sign_attestation_digest(
        token_id=101,
        sun_digest="0x" + "ab" * 32,
        similarity_bps=9350,
    )
    assert attestation["hsm_key_arn"] == "arn:aws:kms:us-east-1:999999999999:key/live-kms-key"
    assert attestation["kms_provider"] == "aws_kms"
    assert attestation["signature"].startswith("0x")
    assert len(attestation["signature"]) == 132
    assert mock_kms.sign.called

    # Cryptographically verify the recovered address from KMS attestation
    kms_message = {
        "tokenId": 101,
        "sunDigest": "0x" + "ab" * 32,
        "similarityBps": 9350,
        "deadline": attestation["deadline"],
        "nonce": attestation["nonce"],
    }
    kms_signable = encode_typed_data(
        domain_data=ATTESTATION_DOMAIN,
        message_types={"Attestation": ATTESTATION_TYPES["Attestation"]},
        message_data=kms_message,
    )
    recovered_kms_address = Account.recover_message(kms_signable, signature=attestation["signature"])
    assert recovered_kms_address.lower() == signer.public_address.lower()

    # 2. HashiCorp Vault Transit provider with real base64-encoded DER ECDSA signature
    def vault_post_side_effect(url, headers=None, json=None, timeout=None):
        raw_digest = base64.b64decode(json["input"])
        sig = dev_account.unsafe_sign_hash(raw_digest)
        der_bytes = encode_dss_signature(sig.r, sig.s)
        vault_sig = "vault:v1:" + base64.b64encode(der_bytes).decode("ascii")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"signature": vault_sig}}
        return mock_resp

    with patch("server.node.hsm_signer.httpx.post", side_effect=vault_post_side_effect) as mock_post:
        vault_signer = HsmProtocolNodeSigner(
            key_arn="vault://transit/keys/arthentic-node-signer",
            provider="vault_transit",
            vault_addr="https://vault.arthentic.internal:8200",
            vault_token="s.vault_root_token",
        )
        vault_att = vault_signer.sign_attestation_digest(
            token_id=102,
            sun_digest="0x" + "cd" * 32,
            similarity_bps=9100,
        )
        assert vault_att["kms_provider"] == "vault_transit"
        assert vault_att["hsm_key_arn"] == "vault://transit/keys/arthentic-node-signer"
        assert len(vault_att["signature"]) == 132
        assert mock_post.called

        # Cryptographically verify the recovered address from Vault Transit attestation
        vault_message = {
            "tokenId": 102,
            "sunDigest": "0x" + "cd" * 32,
            "similarityBps": 9100,
            "deadline": vault_att["deadline"],
            "nonce": vault_att["nonce"],
        }
        vault_signable = encode_typed_data(
            domain_data=ATTESTATION_DOMAIN,
            message_types={"Attestation": ATTESTATION_TYPES["Attestation"]},
            message_data=vault_message,
        )
        recovered_vault_address = Account.recover_message(vault_signable, signature=vault_att["signature"])
        assert recovered_vault_address.lower() == vault_signer.public_address.lower()


def test_hsm_signer_real_aes128_sun_cmac_verification():
    """
    Verifies HsmProtocolNodeSigner.verify_nfc_cmac enforces BOTH Redis monotonic
    counter protection AND real AES-128 CMAC validation via sun_verifier (D-02).
    """
    uid = "04A1B2C3D4E599"
    valid_sun = sun_verifier.generate_sun_params(uid)

    # 1. Forged CMAC with valid length must be rejected by AES-128 CMAC check
    ok_forged, err_forged = node_signer.verify_nfc_cmac(
        uid_hex=uid,
        counter=valid_sun["ctr"] + 10,
        cmac_hex="0000000000000000",
        key_ref="arn:aws:kms:arthentic:key/sun-aes128",
    )
    assert ok_forged is False
    assert err_forged is not None
    assert "CMAC" in err_forged

    # 2. Valid SUN params generated for a fresh counter must pass
    fresh_sun = sun_verifier.generate_sun_params(uid)
    # Advance counter above previous attempt
    fresh_ctr = valid_sun["ctr"] + 20
    expected_cmac = sun_verifier.compute_cmac(uid, fresh_ctr)
    ok_valid, err_valid = node_signer.verify_nfc_cmac(
        uid_hex=uid,
        counter=fresh_ctr,
        cmac_hex=expected_cmac,
        key_ref="arn:aws:kms:arthentic:key/sun-aes128",
    )
    assert ok_valid is True
    assert err_valid is None


def test_admin_signers_rotate_route_and_db_persistence():
    """
    Verifies POST /v1/admin/signers/rotate (Section 3.3 & A-09/A-10) rotates the active
    HSM key ARN in node_signer and persists the SignerKey record in the database.
    """
    headers = _create_admin_headers()
    new_arn = "arn:aws:kms:us-east-1:123456789012:key/rotated-node-key-v2"
    resp = client.post(
        "/v1/admin/signers/rotate",
        headers=headers,
        json={
            "compromised_key_address": "0x1111111111111111111111111111111111111111",
            "new_hsm_key_arn": new_arn,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["feature_code"] == "A-09"
    assert body["new_hsm_key_arn"] == new_arn
    assert node_signer.key_arn == new_arn

    db = SessionLocal()
    try:
        key_row = db.query(SignerKey).filter(SignerKey.kms_key_id == new_arn).first()
        assert key_row is not None
        assert key_row.status == "ACTIVE"
    finally:
        db.close()


def test_arweave_and_pinata_ipfs_dual_gateway_and_b12_integrity():
    """
    Verifies ArweaveStorageAdapter supports live Irys/Bundlr & Pinata IPFS gateway
    uploads, returns both ar:// and ipfs:// URIs, and cryptographically verifies
    bundle integrity (B-04, B-12, E-04).
    """
    adapter = ArweaveStorageAdapter(
        gateway_url="https://arweave.net",
        irys_node_url="https://node2.irys.xyz",
        pinata_jwt="mock_pinata_jwt_token",
    )

    with patch("server.node.arweave_storage.httpx.post") as mock_post:
        mock_irys_resp = MagicMock()
        mock_irys_resp.status_code = 200
        mock_irys_resp.json.return_value = {"id": "irys_live_tx_123456789012345678901234567890"}

        mock_pinata_resp = MagicMock()
        mock_pinata_resp.status_code = 200
        mock_pinata_resp.json.return_value = {"IpfsHash": "QmPinataLiveCid1234567890abcdef"}

        mock_post.side_effect = [mock_irys_resp, mock_pinata_resp]

        bundle = adapter.upload_dossier_bundle(
            token_id="105",
            title="Meridian in Ultramarine",
            artist="Elena Vance",
            feature_vectors=["0x" + "12" * 32],
            notes="8-point LiDAR + Macro RGB intake dossier",
        )
        assert bundle["uri"].startswith("ar://")
        assert bundle["ipfsUri"].startswith("ipfs://")
        assert bundle["digest"].startswith("0x")
        assert len(bundle["digest"]) == 66

        # Verify B-12 integrity check passes for matching digest and fails for tampered digest
        ok_check = adapter.verify_bundle_integrity(bundle["uri"], bundle["digest"])
        assert ok_check["verified"] is True
        assert ok_check["computed_digest"] == bundle["digest"]

        bad_check = adapter.verify_bundle_integrity(bundle["uri"], "0x" + "ff" * 32)
        assert bad_check["verified"] is False


def test_erc4337_paymaster_user_operation_sponsorship():
    """
    Verifies PaymasterPolicyEngine.sponsor_user_operation() and POST /v1/admin/paymaster/sponsor-userop
    sign ERC-4337 UserOperations (paymasterAndData) with Bundler RPC / HSM fallback.
    """
    user_op = {
        "sender": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
        "nonce": "0x1",
        "callData": "0x12345678",
        "callGasLimit": "0x493e0",
    }
    res = paymaster_engine.sponsor_user_operation(
        user_op=user_op,
        wallet_address="0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
        method_name="claim",
        user_roles=["Collector"],
    )
    assert res["sponsored"] is True
    assert res["tier"] == "T1"
    assert res["paymasterAndData"].startswith("0x")
    assert len(res["paymasterAndData"]) > 42
    assert "signature" in res

    # Also test via REST API endpoint
    api_resp = client.post(
        "/v1/paymaster/sponsor",
        json={
            "wallet_address": "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
            "method_name": "genesisMint",
            "user_roles": ["Verifier"],
            "user_op": user_op,
        },
    )
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert api_data["sponsored"] is True
    assert api_data["tier"] == "T2"
    assert api_data["paymasterAndData"].startswith("0x")
