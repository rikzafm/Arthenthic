import pytest
import io
import json
from fastapi.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct
from server.main import app
from server.ml.embedder import EXTRACTOR_VERSION

client = TestClient(app)

def test_get_config():
    response = client.get("/v1/config")
    assert response.status_code == 200
    data = response.json()
    assert data["extractorVersion"] == EXTRACTOR_VERSION
    assert data["minSimilarityBps"] == 8800
    assert data["chainId"] == 84532

def test_auth_challenge_and_verify():
    acct = Account.create()
    addr = acct.address
    res_ch = client.post("/v1/auth/challenge", json={"address": addr})
    assert res_ch.status_code == 200
    ch_data = res_ch.json()
    assert "nonce" in ch_data
    assert "message" in ch_data

    # Sign challenge message with genuine private key
    signed = acct.sign_message(encode_defunct(text=ch_data["message"]))
    sig_hex = "0x" + signed.signature.hex()

    # Verify with genuine signature
    res_vf = client.post("/v1/auth/verify", json={"address": addr, "signature": sig_hex})
    assert res_vf.status_code == 200
    vf_data = res_vf.json()
    assert "session" in vf_data
    assert "Collector" in vf_data["roles"]

    # Replay attack attempt: nonce consumed -> must fail with 401
    res_replay = client.post("/v1/auth/verify", json={"address": addr, "signature": sig_hex})
    assert res_replay.status_code == 401

    # Backdoor attempt with 'debug' -> must fail with 401
    res_debug = client.post("/v1/auth/verify", json={"address": addr, "signature": "debug"})
    assert res_debug.status_code == 401

def test_level1_nfc_verify():
    # 1. Get simulated SUN params
    sim_res = client.get("/v1/verify/simulate-sun")
    assert sim_res.status_code == 200
    sun_params = sim_res.json()

    # 2. Verify Level 1
    vf_res = client.post("/v1/verify/level1", json={"sunParams": sun_params, "tokenId": "101"})
    assert vf_res.status_code == 200
    vf_data = vf_res.json()
    assert vf_data["status"] == "VALID"
    assert "attestation" in vf_data
    assert vf_data["attestation"]["similarityBps"] == 0

    # 3. Replay same counter -> MUST FAIL
    replay_res = client.post("/v1/verify/level1", json={"sunParams": sun_params, "tokenId": "101"})
    assert replay_res.status_code == 400

from server.db.seed import seed_dev_users

def test_capture_and_level2_flow():
    # 1. Upload mock photo + depth
    seed_dev_users()
    login_res = client.post("/auth/login", json={"email": "collector@arthentic.io", "password": "Collector123!"})
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    dummy_img = io.BytesIO()
    from PIL import Image
    im = Image.new("RGB", (100, 100), color=(120, 150, 180))
    im.save(dummy_img, format="JPEG")
    dummy_img.seek(0)

    files = {
        "photo": ("canvas.jpg", dummy_img.getvalue(), "image/jpeg"),
    }
    data = {
        "intrinsics": json.dumps({"fx": 1400.0, "fy": 1400.0, "cx": 50.0, "cy": 50.0}),
        "metadata": json.dumps({"distanceCm": 14, "steadiness": "good"})
    }

    res_cap = client.post("/v1/captures", files=files, data=data, headers=headers)
    assert res_cap.status_code == 200
    cap_id = res_cap.json()["captureId"]

    # 2. Level 2 verify
    res_l2 = client.post("/v1/verify/level2", json={
        "tokenId": "101",
        "captureId": cap_id,
        "extractorVersion": EXTRACTOR_VERSION
    }, headers=headers)
    assert res_l2.status_code == 200
    l2_data = res_l2.json()
    assert "similarityBps" in l2_data
    assert "branches" in l2_data
    assert "attestation" in l2_data

    # 3. Extractor version mismatch -> MUST FAIL
    res_mismatch = client.post("/v1/verify/level2", json={
        "tokenId": "101",
        "captureId": cap_id,
        "extractorVersion": "arthentic-v0.0.1"
    }, headers=headers)
    assert res_mismatch.status_code == 400


