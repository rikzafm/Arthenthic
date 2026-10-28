import io
import json
import pytest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from server.main import app
from server.ml.embedder import embedder, EXTRACTOR_VERSION
from server.ml.depth_features import depth_extractor
from server.ml.similarity import similarity_engine
from server.storage import store

client = TestClient(app)

def create_synthetic_image(seed=42, color_bias=(150, 100, 80)):
    np.random.seed(seed)
    arr = np.random.randint(color_bias[0] - 20, color_bias[0] + 20, (120, 120, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

def create_synthetic_depth(relief_std=0.00045):
    """
    Generate synthetic float32 depth map (128x128).
    relief_std in meters: 0.00045 = 0.45mm (canvas weave), 0.00008 = 0.08mm (flat paper).
    """
    np.random.seed(123)
    z = np.full((128, 128), 0.14, dtype=np.float32)
    noise = np.random.normal(0, relief_std, (128, 128)).astype(np.float32)
    depth = z + noise
    return depth.tobytes()

class TestDepthFeaturesAndEmbedder:
    def test_depth_extractor_detects_canvas_vs_flat_print(self):
        intrinsics = {"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0}
        
        # 1. Genuine canvas depth (roughness >= 0.25mm)
        canvas_depth_bytes = create_synthetic_depth(relief_std=0.00045)
        canvas_feats = depth_extractor.extract_features(canvas_depth_bytes, intrinsics)
        assert canvas_feats["flat_print_passed"] is True
        assert canvas_feats["relief_roughness"] >= 0.25

        # 2. Flat paper print (roughness < 0.20mm)
        flat_depth_bytes = create_synthetic_depth(relief_std=0.00008)
        flat_feats = depth_extractor.extract_features(flat_depth_bytes, intrinsics)
        assert flat_feats["flat_print_passed"] is False
        assert flat_feats["relief_roughness"] < 0.20

    def test_embedder_unit_norm_and_consistency(self):
        img_bytes = create_synthetic_image(seed=10)
        vec1 = embedder.extract_from_bytes(img_bytes)
        vec2 = embedder.extract_from_bytes(img_bytes)

        # L2 norm is 1.0
        assert np.isclose(np.linalg.norm(vec1), 1.0, atol=1e-5)
        # Deterministic consistency
        cos_sim = float(np.dot(vec1, vec2))
        assert np.isclose(cos_sim, 1.0, atol=1e-5)

class TestMultiPointSpatialVerification:
    @pytest.fixture(autouse=True)
    def setup_artwork(self):
        """Enroll an 8-point baseline artwork token for testing."""
        intrinsics = json.dumps({"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0})
        
        genesis_capture_ids = []
        for pt in range(1, 9):
            img = create_synthetic_image(seed=pt * 100)
            depth = create_synthetic_depth(relief_std=0.00045)
            files = {
                "photo": (f"point_{pt}.jpg", img, "image/jpeg"),
                "depth": (f"point_{pt}.bin", depth, "application/octet-stream")
            }
            data = {
                "intrinsics": intrinsics,
                "metadata": json.dumps({"pointIndex": pt, "distanceCm": 14, "steadiness": "Good"})
            }
            res = client.post("/v1/captures", files=files, data=data)
            assert res.status_code == 200
            genesis_capture_ids.append(res.json()["captureId"])

        # Enroll genesis with 8 points
        res_gen = client.post("/v1/genesis/prepare", json={
            "captureIds": genesis_capture_ids,
            "title": "Starry Night Spatial Test",
            "artist": "Vincent van Gogh"
        })
        assert res_gen.status_code == 200
        self.token_id = res_gen.json()["tokenId"]
        self.genesis_capture_ids = genesis_capture_ids

    def test_8_point_genuine_surface_passes_verification(self):
        """
        Verify with matching captures across all 8 spatial points.
        Must return isAuthentic=True, similarityBps >= 8800, and pointsPassed >= 7.
        """
        intrinsics = json.dumps({"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0})
        verify_capture_ids = []
        for pt in range(1, 9):
            # Capture matching point with slight natural jitter
            img = create_synthetic_image(seed=pt * 100)
            depth = create_synthetic_depth(relief_std=0.00045)
            files = {
                "photo": (f"verify_pt_{pt}.jpg", img, "image/jpeg"),
                "depth": (f"verify_pt_{pt}.bin", depth, "application/octet-stream")
            }
            data = {
                "intrinsics": intrinsics,
                "metadata": json.dumps({"pointIndex": pt, "distanceCm": 14, "steadiness": "Good"})
            }
            res = client.post("/v1/captures", files=files, data=data)
            verify_capture_ids.append(res.json()["captureId"])

        # Level 2 verify with all 8 capture IDs
        res_v2 = client.post("/v1/verify/level2", json={
            "tokenId": self.token_id,
            "captureIds": verify_capture_ids,
            "extractorVersion": EXTRACTOR_VERSION
        })
        assert res_v2.status_code == 200
        data = res_v2.json()
        assert data["isAuthentic"] is True
        assert data["similarityBps"] >= 8800
        assert data["pointsPassed"] >= 7
        assert data["totalPoints"] == 8
        assert len(data["pointBreakdown"]) == 8
        assert "attestation" in data
        assert data["attestation"]["similarityBps"] == data["similarityBps"]

    def test_7_of_8_points_pass_tolerance(self):
        """
        7 of 8 points genuine, 1 point degraded/impostor.
        Must still pass with tolerance (>= 7 of 8 points required).
        """
        intrinsics = json.dumps({"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0})
        verify_capture_ids = []
        for pt in range(1, 9):
            if pt == 4:
                # Point 4 is an impostor / corrupted point
                img = create_synthetic_image(seed=9999)
            else:
                img = create_synthetic_image(seed=pt * 100)
            depth = create_synthetic_depth(relief_std=0.00045)
            files = {
                "photo": (f"verify_pt_{pt}.jpg", img, "image/jpeg"),
                "depth": (f"verify_pt_{pt}.bin", depth, "application/octet-stream")
            }
            data = {
                "intrinsics": intrinsics,
                "metadata": json.dumps({"pointIndex": pt, "distanceCm": 14, "steadiness": "Good"})
            }
            res = client.post("/v1/captures", files=files, data=data)
            verify_capture_ids.append(res.json()["captureId"])

        res_v2 = client.post("/v1/verify/level2", json={
            "tokenId": self.token_id,
            "captureIds": verify_capture_ids,
            "extractorVersion": EXTRACTOR_VERSION
        })
        assert res_v2.status_code == 200
        data = res_v2.json()
        assert data["isAuthentic"] is True
        assert data["pointsPassed"] == 7
        assert data["totalPoints"] == 8

    def test_rejection_when_less_than_7_points_pass(self):
        """
        Only 4 points match -> must be rejected (isAuthentic = False).
        """
        intrinsics = json.dumps({"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0})
        verify_capture_ids = []
        for pt in range(1, 9):
            # Points 1-4 match, Points 5-8 are impostor surfaces
            seed = (pt * 100) if pt <= 4 else (pt * 7777)
            img = create_synthetic_image(seed=seed)
            depth = create_synthetic_depth(relief_std=0.00045)
            files = {
                "photo": (f"verify_pt_{pt}.jpg", img, "image/jpeg"),
                "depth": (f"verify_pt_{pt}.bin", depth, "application/octet-stream")
            }
            data = {
                "intrinsics": intrinsics,
                "metadata": json.dumps({"pointIndex": pt, "distanceCm": 14, "steadiness": "Good"})
            }
            res = client.post("/v1/captures", files=files, data=data)
            verify_capture_ids.append(res.json()["captureId"])

        res_v2 = client.post("/v1/verify/level2", json={
            "tokenId": self.token_id,
            "captureIds": verify_capture_ids,
            "extractorVersion": EXTRACTOR_VERSION
        })
        assert res_v2.status_code == 200
        data = res_v2.json()
        assert data["isAuthentic"] is False
        assert data["pointsPassed"] < 7

    def test_flat_print_presentation_attack_rejected(self):
        """
        Photo textures match 100%, but LiDAR depth relief is flat (paper print attack).
        Must be rejected!
        """
        intrinsics = json.dumps({"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0})
        verify_capture_ids = []
        for pt in range(1, 9):
            img = create_synthetic_image(seed=pt * 100)
            # Flat paper depth map: relief_std = 0.08mm
            depth = create_synthetic_depth(relief_std=0.00008)
            files = {
                "photo": (f"verify_pt_{pt}.jpg", img, "image/jpeg"),
                "depth": (f"verify_pt_{pt}.bin", depth, "application/octet-stream")
            }
            data = {
                "intrinsics": intrinsics,
                "metadata": json.dumps({"pointIndex": pt, "distanceCm": 14, "steadiness": "Good"})
            }
            res = client.post("/v1/captures", files=files, data=data)
            verify_capture_ids.append(res.json()["captureId"])

        res_v2 = client.post("/v1/verify/level2", json={
            "tokenId": self.token_id,
            "captureIds": verify_capture_ids,
            "extractorVersion": EXTRACTOR_VERSION
        })
        assert res_v2.status_code == 200
        data = res_v2.json()
        assert data["isAuthentic"] is False
        assert data["branches"]["flatPrintPassed"] is False
