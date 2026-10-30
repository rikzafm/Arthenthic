"""
server/tests/test_wave3_milestone5.py
TDD Test Suite for Wave 3 Milestone 5 (Live Testnet Commissioning & Physical Hardware Trials):
1. scripts/commission_testnet.py: Base Sepolia (84532) & Eth Sepolia (11155111) RPC checks,
   contract manifest verification, Paymaster deposit balance monitor, KMS signer probe,
   and Irys/Pinata storage gateway readiness.
2. server/ml/calibration.py: 8-point 256x192 LiDAR + Macro RGB substrate field calibration
   across Linen Canvas, Wood Panel, Impasto Oil, and Watercolor Cotton.
3. NTAG 424 DNA Tamper-Loop Tag verification: TAMPER_OK vs TAMPER_PERM_OPEN detection
   and integration into /v1/verify & /v1/verify/public (D-15* FLAGGED status).
4. REST API routes: POST /v1/verify/calibrate-substrate & GET /v1/admin/testnet/commissioning-status.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
from fastapi.testclient import TestClient

from server.main import app
from server.crypto.sun import SunVerifier, sun_verifier

REPO_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def test_testnet_commissioning_harness_spec():
    """
    Verifies scripts/commission_testnet.py exists and can execute automated
    pre-flight commissioning checks across Base Sepolia (84532) and Ethereum Sepolia (11155111).
    """
    script_path = REPO_ROOT / "scripts" / "commission_testnet.py"
    assert script_path.exists(), "scripts/commission_testnet.py must exist"

    from scripts.commission_testnet import run_testnet_commissioning

    report = run_testnet_commissioning(mock_rpc=True)
    assert "base_sepolia" in report
    assert "ethereum_sepolia" in report
    assert "paymaster_entrypoint" in report
    assert "kms_signer" in report
    assert "storage_gateways" in report
    assert "overall_ready" in report

    assert report["base_sepolia"]["chain_id"] == 84532
    assert report["ethereum_sepolia"]["chain_id"] == 11155111
    assert report["paymaster_entrypoint"]["deposit_status"] in ("ok", "warning", "empty")
    assert report["kms_signer"]["status"] in ("ok", "simulated")
    assert report["storage_gateways"]["dual_pinning_configured"] is True


def test_substrate_field_calibration_engine():
    """
    Verifies server/ml/calibration.py provides substrate-specific calibration profiles,
    depth SNR estimation for 256x192 LiDAR, ambient lighting normalization, and adaptive thresholds.
    """
    from server.ml.calibration import (
        SubstrateType,
        SubstrateCalibrationEngine,
        substrate_engine,
    )

    # 1. Profiles for all 4 physical substrates
    for sub in (
        SubstrateType.LINEN_CANVAS,
        SubstrateType.WOOD_PANEL,
        SubstrateType.IMPASTO_OIL,
        SubstrateType.WATERCOLOR_COTTON,
    ):
        profile = substrate_engine.get_profile(sub)
        assert profile is not None
        assert profile.baseline_roughness_mm > 0.0
        assert 8000 <= profile.min_similarity_bps <= 9500
        assert 0.0 < profile.depth_weight < 1.0

    # 2. LiDAR 256x192 depth SNR computation
    depth_map = np.full((192, 256), 0.14, dtype=np.float32)
    # Add subtle weave relief pattern
    for y in range(192):
        for x in range(256):
            depth_map[y, x] += np.sin(x * 0.45) * 0.00045

    snr_db = substrate_engine.calculate_depth_snr(depth_map, noise_sigma=0.00005)
    assert snr_db > 10.0, f"Expected SNR > 10 dB, got {snr_db}"

    # 3. Ambient lighting normalization
    dark_frame = np.full((100, 100, 3), 40, dtype=np.uint8)
    normalized = substrate_engine.normalize_lighting(dark_frame, target_lux=500, measured_lux=80)
    assert normalized.mean() > dark_frame.mean()

    # 4. Adaptive substrate evaluation
    # Impasto oil canvas with high surface roughness (1.1mm) should pass with adapted impasto profile
    eval_impasto = substrate_engine.evaluate_substrate_calibration(
        substrate=SubstrateType.IMPASTO_OIL,
        depth_roughness_mm=1.1,
        photo_texture_pct=92,
        ambient_lux=450,
    )
    assert eval_impasto["isAuthentic"] is True
    assert eval_impasto["thresholdBps"] == 8500
    assert eval_impasto["substrate"] == "IMPASTO_OIL"

    # Flat print (0.10mm) on canvas should fail the relief gate
    eval_flat = substrate_engine.evaluate_substrate_calibration(
        substrate=SubstrateType.LINEN_CANVAS,
        depth_roughness_mm=0.10,
        photo_texture_pct=95,
        ambient_lux=500,
    )
    assert eval_flat["isAuthentic"] is False
    assert eval_flat["flatPrintPassed"] is False


def test_ntag_424_dna_tamper_loop_verification():
    """
    Verifies NTAG 424 DNA tamper loop detection:
    - TAMPER_OK passes verification normally.
    - TAMPER_PERM_OPEN detects broken tamper loop and reports is_tampered=True.
    """
    verifier = SunVerifier()
    uid = "04A1B2C3D4E588"
    params = verifier.generate_sun_params(uid=uid)

    # 1. Normal intact tag (TAMPER_OK)
    valid, err, is_tampered = verifier.verify_sun_with_tamper(
        uid=params["uid"],
        ctr=params["ctr"],
        cmac=params["cmac"],
        tamper_status="TAMPER_OK",
    )
    assert valid is True
    assert err is None
    assert is_tampered is False

    # 2. Severed tamper loop (TAMPER_PERM_OPEN)
    params2 = verifier.generate_sun_params(uid=uid)
    valid2, err2, is_tampered2 = verifier.verify_sun_with_tamper(
        uid=params2["uid"],
        ctr=params2["ctr"],
        cmac=params2["cmac"],
        tamper_status="TAMPER_PERM_OPEN",
    )
    assert is_tampered2 is True
    assert "Tamper loop permanently opened" in (err2 or "")


def test_substrate_calibration_and_admin_commissioning_endpoints():
    """
    Verifies:
    1. POST /v1/verify/calibrate-substrate returns substrate recommendations and SNR.
    2. GET /v1/admin/testnet/commissioning-status returns Base Sepolia and Eth Sepolia readiness.
    """
    # 1. Calibrate substrate endpoint
    cal_resp = client.post(
        "/v1/verify/calibrate-substrate",
        json={
            "substrate": "LINEN_CANVAS",
            "ambient_lux": 480,
            "measured_roughness_mm": 0.46,
            "photo_texture_score": 93,
        },
    )
    assert cal_resp.status_code == 200
    cal_data = cal_resp.json()
    assert cal_data["substrate"] == "LINEN_CANVAS"
    assert cal_data["recommended_threshold_bps"] == 8800
    assert cal_data["is_valid_substrate"] is True
    assert "calibrated_score_bps" in cal_data

    # 2. Admin commissioning status endpoint
    admin_resp = client.get("/v1/admin/testnet/commissioning-status")
    assert admin_resp.status_code == 200
    admin_data = admin_resp.json()
    assert "base_sepolia" in admin_data
    assert "ethereum_sepolia" in admin_data
    assert "overall_ready" in admin_data

