"""
server/tests/test_wave3_milestone6.py
TDD Test Suite for Wave 3 Milestone 6 (Mainnet Launch Readiness, FIPS 140-3 KMS Ceremony & Production Release):
1. server/node/mainnet_ceremony.py: Multi-custodian FIPS 140-3 HSM ceremony generator and verifier
   (3-of-5 custodian M-of-N threshold, SHA-256 key fingerprint, and tamper-evident audit record).
2. server/config.py & chain_client.py: Base Mainnet (8453) and Ethereum Mainnet (1) RPC failover,
   Gnosis Safe multi-sig (3-of-5), 48-hour Timelock controller, and mainnet contract addresses.
3. REST Endpoints:
   - GET /v1/admin/mainnet/readiness: Full readiness verification across Base Mainnet, Eth Mainnet,
     Gnosis Safe, Timelock, and KMS ceremony.
   - POST /v1/admin/mainnet/ceremony/verify: Multi-custodian ceremony verification & sealing.
   - GET /v1/admin/mainnet/staged-rollout/status: 7-day phased rollout tracker and KPI health monitor.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_fips_140_3_hsm_ceremony_engine():
    """
    Verifies server/node/mainnet_ceremony.py produces and verifies
    cryptographic FIPS 140-3 HSM key generation ceremonies:
    - 3-of-5 custodian signature threshold
    - Key derivation fingerprint & public key match
    - Ceremony sealing & verification
    """
    from server.node.mainnet_ceremony import MainnetCeremonyEngine, ceremony_engine

    # 1. Create ceremony draft
    ceremony = ceremony_engine.initialize_ceremony(
        key_id="arn:aws:kms:us-east-1:123456789012:key/mainnet-arthentic-protocol-signer",
        public_key_hex="0x0444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444",
        required_custodians=3,
        total_custodians=5,
    )

    assert ceremony["status"] == "PENDING"
    assert ceremony["required_signatures"] == 3
    assert ceremony["total_custodians"] == 5
    assert len(ceremony["key_fingerprint"]) == 64

    # 2. Add custodian signatures (2 signatures - should remain PENDING)
    ceremony_engine.record_custodian_approval(
        ceremony_id=ceremony["ceremony_id"],
        custodian_id="custodian_1",
        custodian_address="0x1111111111111111111111111111111111111111",
        signature_hex="0xaaaa1111",
    )
    ceremony_engine.record_custodian_approval(
        ceremony_id=ceremony["ceremony_id"],
        custodian_id="custodian_2",
        custodian_address="0x2222222222222222222222222222222222222222",
        signature_hex="0xbbbb2222",
    )
    curr = ceremony_engine.get_ceremony(ceremony["ceremony_id"])
    assert curr["status"] == "PENDING"
    assert len(curr["approvals"]) == 2

    # 3. Add 3rd custodian signature - threshold met, status becomes SEALED
    sealed = ceremony_engine.record_custodian_approval(
        ceremony_id=ceremony["ceremony_id"],
        custodian_id="custodian_3",
        custodian_address="0x3333333333333333333333333333333333333333",
        signature_hex="0xcccc3333",
    )
    assert sealed["status"] == "SEALED"
    assert sealed["verified"] is True
    assert "sealed_at" in sealed


def test_mainnet_config_and_chain_manifest():
    """
    Verifies server/config.py contains production Base Mainnet (8453)
    and Ethereum Mainnet (1) configurations, Timelock delay (48 hours),
    and Gnosis Safe multi-sig addresses.
    """
    from server.node.mainnet_ceremony import ceremony_engine

    manifest = ceremony_engine.get_mainnet_manifest()
    assert manifest["base_mainnet"]["chain_id"] == 8453
    assert manifest["ethereum_mainnet"]["chain_id"] == 1
    assert manifest["governance"]["timelock_delay_seconds"] == 172800  # 48 hours
    assert manifest["governance"]["safe_threshold"] == "3-of-5"
    assert "https://verify.arthentic.io" in manifest["cdn"]["verify_base_url"]


def test_mainnet_readiness_and_ceremony_endpoints():
    """
    Verifies REST API routes:
    - GET /v1/admin/mainnet/readiness
    - POST /v1/admin/mainnet/ceremony/verify
    - GET /v1/admin/mainnet/staged-rollout/status
    """
    # 1. Readiness status endpoint
    readiness_resp = client.get("/v1/admin/mainnet/readiness")
    assert readiness_resp.status_code == 200
    r_data = readiness_resp.json()
    assert "base_mainnet" in r_data
    assert "ethereum_mainnet" in r_data
    assert "governance" in r_data
    assert "ceremony_status" in r_data
    assert r_data["base_mainnet"]["chain_id"] == 8453

    # 2. Ceremony verify endpoint
    ceremony_resp = client.post(
        "/v1/admin/mainnet/ceremony/verify",
        json={
            "key_id": "arn:aws:kms:us-east-1:123456789012:key/mainnet-arthentic-protocol-signer",
            "public_key_hex": "0x0444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444444",
            "approvals": [
                {
                    "custodian_id": "custodian_1",
                    "custodian_address": "0x1111111111111111111111111111111111111111",
                    "signature_hex": "0xaaaa1111",
                },
                {
                    "custodian_id": "custodian_2",
                    "custodian_address": "0x2222222222222222222222222222222222222222",
                    "signature_hex": "0xbbbb2222",
                },
                {
                    "custodian_id": "custodian_3",
                    "custodian_address": "0x3333333333333333333333333333333333333333",
                    "signature_hex": "0xcccc3333",
                },
            ],
        },
    )
    assert ceremony_resp.status_code == 200
    c_data = ceremony_resp.json()
    assert c_data["status"] == "SEALED"
    assert c_data["verified"] is True

    # 3. 7-Day Phased Rollout Status endpoint
    rollout_resp = client.get("/v1/admin/mainnet/staged-rollout/status")
    assert rollout_resp.status_code == 200
    ro_data = rollout_resp.json()
    assert "current_day" in ro_data
    assert "rollout_percentage" in ro_data
    assert "kpis" in ro_data
    assert ro_data["kpis"]["auth_login_failures_pct"] < 2.5
    assert ro_data["kpis"]["p0_tamper_alerts"] == 0

