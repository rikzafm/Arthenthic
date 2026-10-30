"""
server/tests/test_wave3_milestone7.py
TDD Test Suite for Wave 3 Milestone 7 (Production Operations, Multi-Region KMS Signer Cluster,
Governance Decentralization Transfer & Staged Rollout SLA Governor):
1. server/node/multi_region_cluster.py:
   - Multi-region KMS protocol signer cluster (primary, secondary, tertiary failover regions)
   - Health status, latency tracking, and automatic / administrative failover
   - Mainnet gas sponsorship pool balance & threshold policy (K-03 / K-05)
2. server/node/governance_transfer.py:
   - On-chain governance decentralization verification
   - Transfer of admin privileges to 3-of-5 Gnosis Safe & 48-hour Timelock
   - Validation that deployer EOA is fully revoked
3. server/monitoring/sla_monitor.py:
   - SLA monitoring engine tracking 5 production KPIs from RELEASE_AND_STAGED_ROLLOUT.md
   - 7-day phased rollout governor with automated P0 emergency pause & rollback trigger
4. REST Endpoints:
   - GET /v1/admin/operations/cluster-status
   - POST /v1/admin/operations/cluster-failover
   - GET /v1/admin/governance/transfer-status
   - GET /v1/admin/operations/sla-status
   - POST /v1/admin/operations/rollout-action
"""

import pytest
from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_multi_region_kms_signer_cluster():
    """
    Verifies server/node/multi_region_cluster.py manages a multi-region KMS signer cluster
    with active failover, regional latency tracking, and Mainnet gas sponsorship pool.
    """
    from server.node.multi_region_cluster import MultiRegionKmsCluster, kms_cluster

    # 1. Cluster initialization and region health
    status = kms_cluster.get_cluster_status()
    assert status["active_region"] in ["us-east-1", "eu-west-1", "ap-southeast-1"]
    assert len(status["regions"]) == 3
    assert status["regions"]["us-east-1"]["healthy"] is True
    assert status["quorum_verified"] is True

    # 2. Regional failover execution
    failover_result = kms_cluster.trigger_failover(
        target_region="eu-west-1",
        reason="Scheduled DR failover rehearsal",
    )
    assert failover_result["success"] is True
    assert failover_result["active_region"] == "eu-west-1"

    updated = kms_cluster.get_cluster_status()
    assert updated["active_region"] == "eu-west-1"

    # Reset back to primary
    kms_cluster.trigger_failover(target_region="us-east-1", reason="Revert to primary")
    assert kms_cluster.get_active_region() == "us-east-1"

    # 3. Mainnet Gas Sponsorship Pool monitoring (K-03 / K-05)
    pool_status = kms_cluster.get_gas_pool_status()
    assert pool_status["chain_id"] == 8453
    assert pool_status["entrypoint_deposit_eth"] >= 0.10
    assert pool_status["health"] in ["HEALTHY", "WARNING", "CRITICAL"]


def test_governance_decentralization_transfer_verification():
    """
    Verifies server/node/governance_transfer.py checks on-chain governance transfer
    to 3-of-5 Gnosis Safe and 48-hour Timelock, ensuring deployer admin is revoked.
    """
    from server.node.governance_transfer import GovernanceTransferVerifier, governance_verifier

    status = governance_verifier.verify_mainnet_governance()
    assert status["is_decentralized"] is True
    assert status["deployer_revoked"] is True
    assert status["gnosis_safe_active"] is True
    assert status["timelock_delay_verified"] is True
    assert status["contracts"]["ArthenticNFT"]["admin"] == "0x1111111111111111111111111111111111111111"
    assert status["contracts"]["MerkleAnchor"]["timelock"] == "0x2222222222222222222222222222222222222222"


def test_sla_monitor_and_automated_rollback_governor():
    """
    Verifies server/monitoring/sla_monitor.py tracks the 5 release KPIs and
    automatically triggers emergency pause/rollback upon P0 breach.
    """
    from server.monitoring.sla_monitor import SlaMonitorEngine, sla_monitor

    # 1. Baseline healthy metrics
    report = sla_monitor.evaluate_kpis()
    assert report["healthy"] is True
    assert report["p0_alerts"] == 0
    assert report["current_rollout_day"] >= 1
    assert report["rollout_percentage"] in [1, 2, 5, 10, 20, 50, 100]

    # 2. Simulate P0 Tamper Report -> Auto-Pause Rollout Triggered
    breach_event = sla_monitor.ingest_telemetry_event(
        event_type="app_lock_bypass_tamper",
        payload={"device_id": "sim_dev_01", "details": "Hardware tamper loop breach"},
    )
    assert breach_event["p0_triggered"] is True
    assert sla_monitor.get_rollout_status()["state"] == "PAUSED"
    assert "P0 Alert: Hardware tamper or token reuse detected" in sla_monitor.get_rollout_status()["pause_reason"]

    # 3. Admin can review and resume or advance rollout
    resumed = sla_monitor.execute_rollout_action(
        action="resume",
        admin_wallet="0x1111111111111111111111111111111111111111",
        reason="Incident investigated and cleared by security team",
    )
    assert resumed["state"] == "ACTIVE"


def test_milestone7_rest_endpoints():
    """
    Verifies REST API endpoints:
    - GET /v1/admin/operations/cluster-status
    - POST /v1/admin/operations/cluster-failover
    - GET /v1/admin/governance/transfer-status
    - GET /v1/admin/operations/sla-status
    - POST /v1/admin/operations/rollout-action
    """
    # 1. Cluster status
    cluster_resp = client.get("/v1/admin/operations/cluster-status")
    assert cluster_resp.status_code == 200
    c_data = cluster_resp.json()
    assert "active_region" in c_data
    assert "regions" in c_data

    # 2. Cluster failover
    failover_resp = client.post(
        "/v1/admin/operations/cluster-failover",
        json={"target_region": "eu-west-1", "reason": "Operational test failover"},
    )
    assert failover_resp.status_code == 200
    assert failover_resp.json()["active_region"] == "eu-west-1"

    # Reset cluster
    client.post(
        "/v1/admin/operations/cluster-failover",
        json={"target_region": "us-east-1", "reason": "Restore primary"},
    )

    # 3. Governance transfer status
    gov_resp = client.get("/v1/admin/governance/transfer-status")
    assert gov_resp.status_code == 200
    g_data = gov_resp.json()
    assert g_data["is_decentralized"] is True
    assert g_data["deployer_revoked"] is True

    # 4. SLA Status
    sla_resp = client.get("/v1/admin/operations/sla-status")
    assert sla_resp.status_code == 200
    s_data = sla_resp.json()
    assert "kpis" in s_data
    assert "rollout_state" in s_data

    # 5. Rollout action (pause / resume)
    action_resp = client.post(
        "/v1/admin/operations/rollout-action",
        json={
            "action": "pause",
            "reason": "Routine pre-deployment verification check",
        },
    )
    assert action_resp.status_code == 200
    assert action_resp.json()["state"] == "PAUSED"

    # Resume rollout
    action_resp2 = client.post(
        "/v1/admin/operations/rollout-action",
        json={"action": "resume", "reason": "Verification passed"},
    )
    assert action_resp2.status_code == 200
    assert action_resp2.json()["state"] == "ACTIVE"
