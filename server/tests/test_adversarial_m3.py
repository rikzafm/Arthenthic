"""
Milestone 3 Adversarial Challenge Test Suite
Empirical verification of EIP-712 Escrow Attestation security and delivery confirmation gates.
Tests all 7 mandatory adversarial challenge vectors plus extended boundary & state-transition attacks.
"""

import time
import secrets
import pytest
from typing import Optional
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient

from server.main import app
from server.node.hsm_signer import TEST_SIGNER_PRIVATE_KEY
from server.db.redis_hotpath import redis_hotpath
from server.db.database import get_db
from server.db.models import EscrowTransaction, MarketplaceListing

client = TestClient(app)


def make_test_attestation(
    token_id: int,
    sun_digest: str = "0x" + "aa" * 32,
    similarity_bps: int = 9500,
    validity_seconds: int = 300,
    private_key: str = TEST_SIGNER_PRIVATE_KEY,
    escrow_address: str = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    chain_id: int = 84532,
    nonce: Optional[str] = None,
    domain_name: str = "ArthenticEscrow",
):
    acct = Account.from_key(private_key)
    deadline = int(time.time()) + validity_seconds
    if not nonce:
        nonce = "0x" + secrets.token_hex(32)

    domain = {
        "name": domain_name,
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": escrow_address,
    }
    types = {
        "Attestation": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "sunDigest", "type": "bytes32"},
            {"name": "similarityBps", "type": "uint16"},
            {"name": "deadline", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    msg = {
        "tokenId": token_id,
        "sunDigest": sun_digest,
        "similarityBps": similarity_bps,
        "deadline": deadline,
        "nonce": nonce,
    }
    signable = encode_typed_data(domain_data=domain, message_types=types, message_data=msg)
    signed = acct.sign_message(signable)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex

    return {
        "attestation": {
            "tokenId": token_id,
            "sunDigest": sun_digest,
            "similarityBps": similarity_bps,
            "deadline": deadline,
            "nonce": nonce,
        },
        "attestation_signature": sig_hex,
    }


def _create_locked_escrow(token_id: int) -> tuple:
    buyer_wallet = f"0xBuyerAdvMetaMask0000000000000000000{token_id}"
    create_res = client.post(
        "/v1/marketplace/listings",
        json={
            "token_id": token_id,
            "artwork_title": f"Adversarial Canvas #{token_id}",
            "artist_name": "Adversarial Artist",
            "artist_wallet": "0xArtist00000000000000000000000000000000001",
            "seller_wallet": "0xSeller00000000000000000000000000000000001",
            "price_amount": 1000.0,
            "asset": "USDC",
        },
    )
    assert create_res.status_code == 200
    listing_id = create_res.json()["listing"]["id"]

    dep_res = client.post(
        f"/v1/marketplace/listings/{listing_id}/deposit",
        json={
            "buyer_wallet": buyer_wallet,
            "wallet_provider": "metamask",
        },
    )
    assert dep_res.status_code == 200
    escrow_id = dep_res.json()["escrow"]["id"]
    return escrow_id, buyer_wallet


# ==============================================================================
# Challenge 1: Raw Booleans Bypass Attempts (Without Attestation)
# ==============================================================================

def test_challenge_bypass_with_raw_booleans():
    """Attack: Submit raw booleans (l1_nfc_verified=True, has_pro_lidar=True, l2_similarity_score=0.99) without attestation."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7001)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "l1_nfc_verified": True,
            "has_pro_lidar": True,
            "l2_similarity_score": 0.99,
        },
    )
    assert res.status_code == 400
    assert "Missing required EIP-712 Protocol Node attestation" in res.json()["detail"]


def test_challenge_bypass_with_legacy_delivery_signature():
    """Attack: Submit legacy delivery_signature with booleans but no attestation structure."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7002)
    fake_sig = "0x" + "99" * 65
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "l1_nfc_verified": True,
            "has_pro_lidar": True,
            "delivery_signature": fake_sig,
        },
    )
    assert res.status_code == 400
    assert "Missing required EIP-712 Protocol Node attestation" in res.json()["detail"]


def test_challenge_bypass_with_empty_payload():
    """Attack: Submit empty payload or missing attestation."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7003)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={"buyer_wallet": buyer_wallet},
    )
    assert res.status_code == 400
    assert "Missing required EIP-712 Protocol Node attestation" in res.json()["detail"]


# ==============================================================================
# Challenge 2: Attestation Nonce Replay Attacks
# ==============================================================================

def test_challenge_replay_nonce_on_different_escrow():
    """Attack: Replay a previously consumed attestation nonce on a distinct escrow (must return 400/409)."""
    escrow_id_1, buyer_wallet_1 = _create_locked_escrow(token_id=7010)
    escrow_id_2, buyer_wallet_2 = _create_locked_escrow(token_id=7011)

    shared_nonce = "0x" + secrets.token_hex(32)

    # Legitimate first release
    payload_1 = make_test_attestation(token_id=7010, nonce=shared_nonce)
    res_1 = client.post(
        f"/v1/marketplace/escrows/{escrow_id_1}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet_1,
            "attestation": payload_1["attestation"],
            "attestation_signature": payload_1["attestation_signature"],
        },
    )
    assert res_1.status_code == 200

    # Attacker tries to reuse the same nonce on escrow 2
    payload_2 = make_test_attestation(token_id=7011, nonce=shared_nonce)
    res_2 = client.post(
        f"/v1/marketplace/escrows/{escrow_id_2}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet_2,
            "attestation": payload_2["attestation"],
            "attestation_signature": payload_2["attestation_signature"],
        },
    )
    assert res_2.status_code in (400, 409)
    assert "Anti-replay violation: Nonce" in res_2.json()["detail"]


def test_challenge_replay_exact_same_request():
    """Attack: Re-submit the exact same confirmation request on already released escrow."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7012)
    nonce = "0x" + secrets.token_hex(32)
    payload = make_test_attestation(token_id=7012, nonce=nonce)

    res_1 = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res_1.status_code == 200

    # Repeat exact same request
    res_2 = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    # Must fail because status is no longer LOCKED
    assert res_2.status_code == 400
    assert "Escrow cannot be released from status DELIVERY_VERIFIED_RELEASED" in res_2.json()["detail"]


def test_challenge_replay_pre_consumed_redis_nonce():
    """Attack: Submit attestation whose nonce was already marked used in redis."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7013)
    preloaded_nonce = "0x" + secrets.token_hex(32)
    # Manually lock nonce in redis hotpath
    redis_hotpath.set_attestation_nonce(preloaded_nonce, ttl_seconds=600)
    assert redis_hotpath.is_nonce_used(preloaded_nonce) is True

    payload = make_test_attestation(token_id=7013, nonce=preloaded_nonce)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code in (400, 409)
    assert "Anti-replay violation: Nonce" in res.json()["detail"]


# ==============================================================================
# Challenge 3: Expired Deadline Attacks
# ==============================================================================

def test_challenge_expired_deadline_in_past():
    """Attack: Submit attestation with deadline expired 60 seconds ago."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7020)
    payload = make_test_attestation(token_id=7020, validity_seconds=-60)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Attestation deadline expired" in res.json()["detail"]


def test_challenge_expired_deadline_exact_current_time():
    """Attack: Submit attestation with deadline == current_time."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7021)
    now = int(time.time())
    payload = make_test_attestation(token_id=7021, validity_seconds=0)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Attestation deadline expired" in res.json()["detail"]


def test_challenge_expired_deadline_zero():
    """Attack: Submit attestation with deadline = 0."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7022)
    # Manual craft with deadline = 0
    acct = Account.from_key(TEST_SIGNER_PRIVATE_KEY)
    nonce = "0x" + secrets.token_hex(32)
    msg = {
        "tokenId": 7022,
        "sunDigest": "0x" + "11" * 32,
        "similarityBps": 9000,
        "deadline": 0,
        "nonce": nonce,
    }
    domain = {
        "name": "ArthenticEscrow",
        "version": "1",
        "chainId": 84532,
        "verifyingContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    }
    types = {
        "Attestation": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "sunDigest", "type": "bytes32"},
            {"name": "similarityBps", "type": "uint16"},
            {"name": "deadline", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    signable = encode_typed_data(domain_data=domain, message_types=types, message_data=msg)
    sig_hex = acct.sign_message(signable).signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": msg,
            "attestation_signature": sig_hex,
        },
    )
    assert res.status_code == 400
    assert "Attestation deadline expired" in res.json()["detail"]


# ==============================================================================
# Challenge 4: Similarity Threshold Boundary (8499 vs 8500 bps)
# ==============================================================================

def test_challenge_similarity_8499_bps_boundary():
    """Attack: Submit attestation with similarityBps = 8499 (84.99% — strictly below 8500)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7030)
    payload = make_test_attestation(token_id=7030, similarity_bps=8499)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "L2 Surface Similarity" in res.json()["detail"]
    assert "below threshold of 85.0%" in res.json()["detail"]


def test_challenge_similarity_8500_bps_boundary_passes():
    """Control: Submit attestation with similarityBps = 8500 (85.00% — exactly at threshold)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7031)
    payload = make_test_attestation(token_id=7031, similarity_bps=8500)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["escrow"]["status"] == "DELIVERY_VERIFIED_RELEASED"
    assert res.json()["escrow"]["l2_similarity_score"] == 0.85


def test_challenge_similarity_pydantic_bounds():
    """Attack: Submit out-of-range similarityBps (-1 or 10001)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7032)
    # ge=0, le=10000 enforced by Pydantic
    res_neg = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": {
                "tokenId": 7032,
                "sunDigest": "0x" + "11" * 32,
                "similarityBps": -1,
                "deadline": int(time.time()) + 300,
                "nonce": "0x" + "22" * 32,
            },
            "attestation_signature": "0x" + "33" * 65,
        },
    )
    assert res_neg.status_code == 422

    res_overflow = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": {
                "tokenId": 7032,
                "sunDigest": "0x" + "11" * 32,
                "similarityBps": 10001,
                "deadline": int(time.time()) + 300,
                "nonce": "0x" + "22" * 32,
            },
            "attestation_signature": "0x" + "33" * 65,
        },
    )
    assert res_overflow.status_code == 422


# ==============================================================================
# Challenge 5: Forged Attestation Signed by Untrusted Random Key
# ==============================================================================

def test_challenge_forged_untrusted_key_rejected():
    """Attack: Generate random private key, sign valid EIP-712 payload. Must return 403."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7040)
    rogue_account = Account.create()
    rogue_key = rogue_account.key.hex()

    payload = make_test_attestation(token_id=7040, private_key=rogue_key)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "Invalid protocol node attestation signature" in res.json()["detail"]
    assert "is not an authorized Protocol Node" in res.json()["detail"]


def test_challenge_malformed_signature_syntax():
    """Attack: Submit corrupt/truncated signature bytes."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7041)
    payload = make_test_attestation(token_id=7041)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": "0xnot_a_valid_hex_signature",
        },
    )
    assert res.status_code == 400
    assert "Invalid protocol node attestation signature" in res.json()["detail"]


def test_challenge_wrong_chain_id_signature():
    """Attack: Attestation signed for Ethereum Mainnet (chainId=1) instead of Base Sepolia (chainId=84532)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7042)
    # Sign with authorized key, but wrong chain_id
    payload = make_test_attestation(token_id=7042, chain_id=1)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    # Because chainId mismatch causes ecrecover to yield a different address, it must be rejected with 403
    assert res.status_code == 403
    assert "is not an authorized Protocol Node" in res.json()["detail"]


def test_challenge_tampered_payload_after_signing():
    """Attack: Sign attestation with similarityBps=8500, but attacker tampers similarityBps=9999 in transmission."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=7043)
    payload = make_test_attestation(token_id=7043, similarity_bps=8500)
    # Tamper payload
    payload["attestation"]["similarityBps"] = 9999
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    # Tampering invalidates the signature, yielding an unauthorized recovered address -> 403
    assert res.status_code == 403
    assert "is not an authorized Protocol Node" in res.json()["detail"]


# ==============================================================================
# Challenge 6: Attestation for Token A on Escrow for Token B
# ==============================================================================

def test_challenge_token_id_mismatch():
    """Attack: Use attestation for token A (8001) on an escrow for token B (8002). Must return 400."""
    escrow_id_b, buyer_wallet_b = _create_locked_escrow(token_id=8002)
    # Generate attestation specifically for token 8001
    payload_a = make_test_attestation(token_id=8001)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id_b}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet_b,
            "attestation": payload_a["attestation"],
            "attestation_signature": payload_a["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Attestation token ID does not match escrow listing" in res.json()["detail"]
    assert "tokenId (8001) does not match escrow tokenId (8002)" in res.json()["detail"]


def test_challenge_token_id_string_vs_int():
    """Attack / Edge Case: Token ID provided as string '8003' matching integer 8003."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=8003)
    payload = make_test_attestation(token_id=8003)
    # Pass as string in attestation
    payload["attestation"]["tokenId"] = "8003"

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


# ==============================================================================
# Challenge 7: Confirm Delivery from Different Buyer Wallet
# ==============================================================================

def test_challenge_unauthorized_buyer_wallet():
    """Attack: A different caller wallet tries to trigger release on buyer's escrow. Must return 403."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=9001)
    payload = make_test_attestation(token_id=9001)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": "0xImposterBuyer000000000000000000000000099",
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "Unauthorized: Only depositing buyer may confirm delivery" in res.json()["detail"]


def test_challenge_buyer_wallet_case_insensitivity():
    """Edge Case: Buyer wallet matching case-insensitively (0xAbC... vs 0xabc...)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=9002)
    payload = make_test_attestation(token_id=9002)

    # Invert case of buyer_wallet
    case_mixed_wallet = ""
    for ch in buyer_wallet:
        if ch.isalpha():
            case_mixed_wallet += ch.lower() if ch.isupper() else ch.upper()
        else:
            case_mixed_wallet += ch

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": case_mixed_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


# ==============================================================================
# Challenge 8: State Machine & Gate Enforcement
# ==============================================================================

def test_challenge_hardware_gate_l1_false():
    """Attack: Pass l1_nfc_verified=False with valid attestation. Must fail with 400."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=9010)
    payload = make_test_attestation(token_id=9010)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "l1_nfc_verified": False,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Invariant #3 Violation: Level 1 NFC" in res.json()["detail"]


def test_challenge_hardware_gate_lidar_false():
    """Attack: Pass has_pro_lidar=False with valid attestation. Must fail with 403 (A6 Gate)."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=9011)
    payload = make_test_attestation(token_id=9011)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "has_pro_lidar": False,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "A6 Hardware Tier Gate" in res.json()["detail"]


def test_challenge_disputed_escrow_cannot_be_released():
    """Attack: Attempt to confirm delivery on an escrow that has been disputed. Must return 400."""
    escrow_id, buyer_wallet = _create_locked_escrow(token_id=9012)
    # Dispute escrow first
    disp_res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/dispute",
        json={
            "caller_wallet": buyer_wallet,
            "reason": "Physical canvas tear detected during intake.",
            "evidence_uri": "ipfs://QmDisputeDamageEvidence",
        },
    )
    assert disp_res.status_code == 200

    payload = make_test_attestation(token_id=9012)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Escrow cannot be released from status DISPUTED" in res.json()["detail"]


def test_challenge_nonexistent_escrow_404():
    """Attack: Attempt to confirm delivery on a non-existent escrow UUID. Must return 404."""
    fake_escrow_id = "00000000-0000-0000-0000-000000000000"
    payload = make_test_attestation(token_id=9013)
    res = client.post(
        f"/v1/marketplace/escrows/{fake_escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": "0xBuyer000000000000000000000000000000000001",
            "attestation": payload["attestation"],
            "attestation_signature": payload["attestation_signature"],
        },
    )
    assert res.status_code == 404
    assert "Escrow transaction not found" in res.json()["detail"]
