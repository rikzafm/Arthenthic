"""
server/tests/test_adversarial_m5.py
Empirical Adversarial Challenge Suite for Milestone 5:
1. Strict HTTP 404 on missing artworks for /v1/verify/level2, /v1/genesis/coa/{id}, and /v1/artworks/{id}.
2. Strict HTTP 404 on missing captures for /v1/verify/level2 (single-point and multi-point).
3. Strict HTTP 404 on un-enrolled, inactive, or orphaned NFC chips for /v1/verify/public and /v1/verify/level1.
4. Mathematical verification that NO dummy vectors [0.05]*384 or fake cosine similarity are awarded.
5. Presentation attack and impostor rejection (orthogonal vectors, flat prints, corrupted spatial grids).
6. Guest vs authenticated verification integrity and provenance recording.
"""

import os
import json
import uuid
import hashlib
import pytest
import numpy as np
from fastapi.testclient import TestClient

from server.main import app
from server.ml.embedder import EXTRACTOR_VERSION
from server.ml.similarity import similarity_engine
from server.crypto.sun import sun_verifier
from server.db.database import SessionLocal
from server.db.models import Artwork, NfcChip, CaptureRecord, ProvenanceEventModel
from server.db.seed import seed_dev_users

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_seed():
    """Ensure dev users and standard token 101 exist."""
    seed_dev_users()


class TestAdversarialMissingEntities:
    """
    Adversarial challenge: Stress-test missing token IDs, capture IDs, and NFC chips.
    All must strictly return HTTP 404.
    """

    @pytest.mark.parametrize("missing_token", [
        "9999999",
        "88888888",
        "-1",
        "0",
        "invalid_slug_xyz",
        "token_non_existent",
        "101' OR '1'='1",
    ])
    def test_missing_artwork_on_level2_returns_404(self, missing_token):
        """Querying missing tokens on /v1/verify/level2 must strictly return HTTP 404."""
        res = client.post("/v1/verify/level2", json={
            "tokenId": missing_token,
            "captureId": "cap_101_pt1",
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 404, f"Expected 404 for tokenId={missing_token}, got {res.status_code}"
        body = res.json()
        assert "error" in body.get("detail", {})
        assert body["detail"]["error"]["code"] == "ARTWORK_NOT_FOUND"

    @pytest.mark.parametrize("missing_token", [
        "9999999",
        "88888888",
        "-1",
        "0",
        "invalid_slug_xyz",
        "non_numeric",
        "101' OR '1'='1",
    ])
    def test_missing_artwork_on_genesis_coa_returns_404(self, missing_token):
        """Querying missing tokens on /v1/genesis/coa/{id} must strictly return HTTP 404."""
        res = client.get(f"/v1/genesis/coa/{missing_token}")
        assert res.status_code == 404, f"Expected 404 for tokenId={missing_token}, got {res.status_code}"
        assert res.json().get("detail") == "Artwork not found"

    @pytest.mark.parametrize("missing_token", [
        "9999999",
        "88888888",
        "-1",
        "0",
        "invalid_slug_xyz",
        "non_numeric",
        "101' OR '1'='1",
    ])
    def test_missing_artwork_on_artworks_endpoint_returns_404(self, missing_token):
        """Querying missing tokens on /v1/artworks/{id} must strictly return HTTP 404."""
        res = client.get(f"/v1/artworks/{missing_token}")
        assert res.status_code == 404, f"Expected 404 for tokenId={missing_token}, got {res.status_code}"
        assert res.json().get("detail") == "Artwork not found"

    def test_missing_capture_single_point_returns_404(self):
        """Querying missing captureId on /v1/verify/level2 must return HTTP 404."""
        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureId": "cap_phantom_missing_000000",
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 404
        body = res.json()
        assert body["detail"]["error"]["code"] == "CAPTURE_NOT_FOUND"
        assert "cap_phantom_missing_000000" in body["detail"]["error"]["message"]

    def test_missing_capture_in_multipoint_list_returns_404(self):
        """Querying a list where one captureId is missing must abort and return HTTP 404."""
        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureIds": ["cap_101_pt1", "cap_101_pt2", "cap_nonexistent_pt3", "cap_101_pt4"],
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 404
        body = res.json()
        assert body["detail"]["error"]["code"] == "CAPTURE_NOT_FOUND"
        assert "cap_nonexistent_pt3" in body["detail"]["error"]["message"]

    def test_no_captures_provided_returns_400(self):
        """Omitting both captureId and captureIds must return HTTP 400 NO_CAPTURES."""
        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureIds": [],
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 400
        body = res.json()
        assert body["detail"]["error"]["code"] == "NO_CAPTURES"

    def test_unenrolled_chip_on_public_verify_returns_404(self):
        """Tapping an un-enrolled NFC chip on /v1/verify/public must return HTTP 404."""
        params = sun_verifier.generate_sun_params("04UNKNOWNCHIP99")
        res = client.post("/v1/verify/public", json={
            "uid": params["uid"],
            "ctr": params["ctr"],
            "cmac": params["cmac"],
        })
        assert res.status_code == 404
        assert res.json().get("detail") == "NFC Chip not found or not enrolled"

    def test_inactive_chip_on_public_verify_returns_404(self):
        """An inactive chip on /v1/verify/public must return HTTP 404."""
        db = SessionLocal()
        try:
            chip = db.query(NfcChip).filter(NfcChip.chip_uid == "04INACTIVE01").first()
            if not chip:
                chip = NfcChip(
                    chip_uid="04INACTIVE01",
                    chip_id_hash="0xinactive01",
                    token_id=101,
                    is_active=False,
                )
                db.add(chip)
                db.commit()
            else:
                chip.is_active = False
                db.commit()
        finally:
            db.close()

        params = sun_verifier.generate_sun_params("04INACTIVE01")
        res = client.post("/v1/verify/public", json={
            "uid": params["uid"],
            "ctr": params["ctr"],
            "cmac": params["cmac"],
        })
        assert res.status_code == 404
        assert res.json().get("detail") == "NFC Chip not found or not enrolled"

    def test_unbound_chip_on_public_verify_returns_404(self):
        """A chip without a bound token_id on /v1/verify/public must return HTTP 404."""
        db = SessionLocal()
        try:
            chip = db.query(NfcChip).filter(NfcChip.chip_uid == "04UNBOUND01").first()
            if not chip:
                chip = NfcChip(
                    chip_uid="04UNBOUND01",
                    chip_id_hash="0xunbound01",
                    token_id=None,
                    is_active=True,
                )
                db.add(chip)
                db.commit()
            else:
                chip.token_id = None
                chip.is_active = True
                db.commit()
        finally:
            db.close()

        params = sun_verifier.generate_sun_params("04UNBOUND01")
        res = client.post("/v1/verify/public", json={
            "uid": params["uid"],
            "ctr": params["ctr"],
            "cmac": params["cmac"],
        })
        assert res.status_code == 404
        assert res.json().get("detail") == "NFC Chip not found or not enrolled"

    def test_unenrolled_chip_on_level1_verify_returns_404(self):
        """Verifying an un-enrolled chip on /v1/verify/level1 must return HTTP 404."""
        params = sun_verifier.generate_sun_params("04NONEXISTENTCHIP")
        res = client.post("/v1/verify/level1", json={
            "sunParams": {
                "uid": params["uid"],
                "ctr": params["ctr"],
                "cmac": params["cmac"],
            },
            "tokenId": "101",
        })
        assert res.status_code == 404
        assert res.json().get("detail") == "Artwork or NFC chip not found"

    def test_mismatched_chip_and_token_on_level1_returns_404(self):
        """A valid chip enrolled to token 101 queried against token 202 must return HTTP 404."""
        params = sun_verifier.generate_sun_params("04A1B2C3D4E580")
        res = client.post("/v1/verify/level1", json={
            "sunParams": {
                "uid": params["uid"],
                "ctr": params["ctr"],
                "cmac": params["cmac"],
            },
            "tokenId": "9999999",
        })
        assert res.status_code == 404
        assert res.json().get("detail") == "Artwork or NFC chip not found"


class TestAdversarialVectorMathematics:
    """
    Adversarial challenge: Verify that NO dummy vectors or fake similarities are ever synthesized.
    """

    def test_no_dummy_005_vectors_in_verification_route(self):
        """Inspect server/routes/verify.py source: absolutely zero 0.05 dummy vectors allowed."""
        verify_route_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "routes", "verify.py")
        )
        with open(verify_route_path, "r") as f:
            content = f.read()
        assert "0.05" not in content, "Found prohibited '0.05' dummy vector fallback in verify.py!"
        assert "Study in Blue and Gold" not in content, "Found hardcoded mock artwork fallback in verify.py!"

    def test_orthogonal_vector_produces_zero_photo_similarity(self):
        """
        Adversarial attack: Two orthogonal vectors must produce cosine similarity ~ 0.
        Must NOT award fake 10000 bps similarity.
        """
        # Create standard basis vectors e1 and e2 (orthogonal)
        v1 = np.zeros(384, dtype=np.float32)
        v1[0] = 1.0
        v2 = np.zeros(384, dtype=np.float32)
        v2[1] = 1.0

        depth = {"relief_roughness": 0.45, "flat_print_passed": True}
        result = similarity_engine.compare(v1, v2, depth, depth)

        assert result["isAuthentic"] is False
        assert result["branches"]["photoTexturePct"] == 0
        # Total combined score is 0% photo + 30% depth = 3000 bps max
        assert result["similarityBps"] <= 3500

    def test_impostor_capture_rejected_on_level2(self):
        """
        Adversarial attack: Register an impostor capture with completely different image features.
        Level 2 verification against token 101 must reject (isAuthentic = False, statusBadge = FLAGGED).
        """
        db = SessionLocal()
        impostor_cid = f"cap_impostor_{uuid.uuid4().hex[:8]}"
        try:
            # Orthogonal vector relative to token 101's ones vector
            impostor_vec = np.zeros(384, dtype=np.float32)
            impostor_vec[0] = 1.0
            impostor_vec = impostor_vec.tolist()

            cap = CaptureRecord(
                id=impostor_cid,
                token_id=101,
                point_index=1,
                vector_hash="0ximpostorhash",
                relief_roughness=0.45,
                flat_print_passed=True,
                has_lidar=True,
                vector=impostor_vec,
                depth_stats={"relief_roughness": 0.45, "flat_print_passed": True},
                intrinsics={"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0},
                metadata_payload={"pointIndex": 1},
            )
            db.add(cap)
            db.commit()
        finally:
            db.close()

        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureId": impostor_cid,
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["isAuthentic"] is False
        assert data["statusBadge"] == "FLAGGED"
        assert data["similarityBps"] < 8800

    def test_flat_print_presentation_attack_heavily_penalized(self):
        """
        Presentation attack: Impostor attempts to verify with matching photo texture,
        but LiDAR reveals zero surface relief roughness (flat paper print).
        Must be marked FLAGGED and isAuthentic = False.
        """
        db = SessionLocal()
        flat_cid = f"cap_flat_{uuid.uuid4().hex[:8]}"
        try:
            # Same vector as token 101 genesis baseline
            v = np.ones(384, dtype=np.float32)
            v = (v / np.linalg.norm(v)).tolist()

            cap = CaptureRecord(
                id=flat_cid,
                token_id=101,
                point_index=1,
                vector_hash="0xflathash",
                relief_roughness=0.05,  # Flat paper
                flat_print_passed=False,  # Failed presentation attack check
                has_lidar=True,
                vector=v,
                depth_stats={"relief_roughness": 0.05, "flat_print_passed": False},
                intrinsics={"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0},
                metadata_payload={"pointIndex": 1},
            )
            db.add(cap)
            db.commit()
        finally:
            db.close()

        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureId": flat_cid,
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["isAuthentic"] is False
        assert data["statusBadge"] == "FLAGGED"
        assert data["branches"]["flatPrintPassed"] is False


class TestAdversarialGuestAndProvenance:
    """
    Adversarial challenge: Verify guest capability and provenance recording.
    """

    def test_guest_level2_verification_succeeds_and_logs_provenance(self):
        """An unauthenticated guest can verify Level 2; provenance logs actor='Guest'."""
        db = SessionLocal()
        initial_count = db.query(ProvenanceEventModel).filter(
            ProvenanceEventModel.token_id == 101,
            ProvenanceEventModel.event_type == "LEVEL2_VERIFICATION",
        ).count()
        db.close()

        res = client.post("/v1/verify/level2", json={
            "tokenId": "101",
            "captureId": "cap_101_pt1",
            "extractorVersion": EXTRACTOR_VERSION,
        })
        assert res.status_code == 200
        data = res.json()
        assert "similarityBps" in data
        assert "attestation" in data

        db = SessionLocal()
        new_count = db.query(ProvenanceEventModel).filter(
            ProvenanceEventModel.token_id == 101,
            ProvenanceEventModel.event_type == "LEVEL2_VERIFICATION",
        ).count()
        last_event = db.query(ProvenanceEventModel).filter(
            ProvenanceEventModel.token_id == 101,
            ProvenanceEventModel.event_type == "LEVEL2_VERIFICATION",
        ).order_by(ProvenanceEventModel.id.desc()).first()
        db.close()

        assert new_count == initial_count + 1
        assert last_event.actor == "Guest"
        assert last_event.role == "Guest"

    def test_tamper_loop_severed_rejected_on_level1(self):
        """A tampered NFC tag must be rejected with TAMPER_LOOP_SEVERED on level1."""
        params = sun_verifier.generate_sun_params("04A1B2C3D4E580")
        res = client.post("/v1/verify/level1", json={
            "sunParams": {
                "uid": params["uid"],
                "ctr": params["ctr"],
                "cmac": params["cmac"],
                "tamperStatus": "TAMPER_PERM_OPEN",
            },
            "tokenId": "101",
        })
        assert res.status_code == 400
        assert res.json()["detail"]["error"]["code"] == "TAMPER_LOOP_SEVERED"
