import json
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from server.crypto.sun import sun_verifier
from server.crypto.attestation import attestation_signer
from server.ml.embedder import EXTRACTOR_VERSION
from server.ml.similarity import similarity_engine
from server.storage import store

router = APIRouter(prefix="/v1/verify", tags=["verify"])

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        # In prototype mode, allow fallback session
        return {"address": "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d", "roles": ["Collector"]}
    token = authorization.replace("Bearer ", "").strip()
    session = store.sessions.get(token)
    if not session:
        # For prototype smooth testing, allow test bearer
        return {"address": "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d", "roles": ["Collector"]}
    return session

class SunParams(BaseModel):
    uid: str
    ctr: int
    cmac: str

class Level1Request(BaseModel):
    sunParams: SunParams
    tokenId: Optional[str] = "101"

class Level2Request(BaseModel):
    tokenId: str
    captureId: Optional[str] = None
    captureIds: Optional[List[str]] = None
    extractorVersion: str = EXTRACTOR_VERSION
    sunParams: Optional[SunParams] = None

@router.get("/simulate-sun")
def get_simulated_sun_params(uid: str = "04A1B2C3D4E5F6"):
    """
    Debug helper: Issues valid next simulated SUN parameters (incremented counter + CMAC).
    """
    return sun_verifier.generate_sun_params(uid)

@router.post("/level1")
def verify_level1(req: Level1Request, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Level 1: Tap NFC chip (SUN cryptographic verification)
    Checks SUN authenticity and rejects counter replays.
    Returns signed EIP-712 attestation.
    """
    valid, err = sun_verifier.verify_sun(req.sunParams.uid, req.sunParams.ctr, req.sunParams.cmac)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_VERIFICATION_FAILED", "message": err}}
        )

    sun_digest = attestation_signer.compute_sun_digest(
        req.sunParams.uid,
        req.sunParams.ctr,
        req.sunParams.cmac
    )

    token_int = int(req.tokenId) if req.tokenId.isdigit() else 101

    attestation = attestation_signer.create_attestation(
        token_id=token_int,
        sun_digest=sun_digest,
        similarity_bps=0 # Level 1 chip verification
    )

    store.add_provenance_event(
        token_id=req.tokenId,
        event_type="LEVEL1_VERIFICATION",
        actor=user.get("address", "0x"),
        role="Collector",
        details=f"NFC SUN chip verified (uid: {req.sunParams.uid}, ctr: {req.sunParams.ctr})"
    )

    return {
        "status": "VALID",
        "level": 1,
        "ctr": req.sunParams.ctr,
        "attestation": attestation
    }

@router.post("/level2")
def verify_level2(req: Level2Request, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Level 2: Camera + LiDAR surface fingerprint matching against genesis baseline.
    Supports single-point capture or 8-point spatial grid verification.
    """
    # 1. Reject if extractor version differs
    if req.extractorVersion != EXTRACTOR_VERSION:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "EXTRACTOR_VERSION_MISMATCH",
                    "message": f"Server extractor is {EXTRACTOR_VERSION}, client sent {req.extractorVersion}"
                }
            }
        )

    artwork = store.artworks.get(req.tokenId)
    if not artwork:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ARTWORK_NOT_FOUND", "message": f"Artwork token {req.tokenId} not found"}}
        )

    # 2. Collect capture IDs
    capture_ids = req.captureIds if req.captureIds else ([req.captureId] if req.captureId else [])
    if not capture_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NO_CAPTURES", "message": "Either captureId or captureIds must be provided"}}
        )

    # Retrieve captures
    captures = []
    for cid in capture_ids:
        cap = store.captures.get(cid)
        if not cap:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "CAPTURE_NOT_FOUND", "message": f"Capture {cid} not found"}}
            )
        captures.append(cap)

    # 3. Calculate similarity (multi-point vs single point)
    is_multi_point = len(captures) > 1 or "genesis_points" in artwork and len(captures) > 1
    if is_multi_point:
        verify_points = []
        for idx, cap in enumerate(captures):
            pt_idx = cap.get("metadata", {}).get("pointIndex", idx + 1)
            verify_points.append({
                "pointIndex": pt_idx,
                "vector": cap["vector"],
                "depth_stats": cap["depth_stats"]
            })

        genesis_points = artwork.get("genesis_points", [{
            "pointIndex": 1,
            "vector": artwork["genesis_vector"],
            "depth_stats": artwork["genesis_depth"]
        }])

        result = similarity_engine.compare_multipoint(genesis_points, verify_points)
    else:
        capture = captures[0]
        genesis_vec = artwork["genesis_vector"]
        verify_vec = capture["vector"]
        genesis_depth = artwork["genesis_depth"]
        verify_depth = capture["depth_stats"]
        result = similarity_engine.compare(genesis_vec, verify_vec, genesis_depth, verify_depth)

    # Compute SUN digest (if present or mock)
    if req.sunParams:
        sun_digest = attestation_signer.compute_sun_digest(
            req.sunParams.uid, req.sunParams.ctr, req.sunParams.cmac
        )
    else:
        sun_digest = "0x" + "0" * 64

    token_int = int(req.tokenId) if req.tokenId.isdigit() else 101

    attestation = attestation_signer.create_attestation(
        token_id=token_int,
        sun_digest=sun_digest,
        similarity_bps=result["similarityBps"]
    )

    pass_details = f"Points passed: {result.get('pointsPassed', 1)}/{result.get('totalPoints', 1)}" if is_multi_point else ""
    store.add_provenance_event(
        token_id=req.tokenId,
        event_type="LEVEL2_VERIFICATION",
        actor=user.get("address", "0x"),
        role="Collector",
        details=f"Surface fingerprint scan {'AUTHENTIC' if result['isAuthentic'] else 'FAILED'}: {result['similarityBps'] / 100:.1f}% similarity. {pass_details}".strip()
    )

    response_payload = {
        "isAuthentic": result["isAuthentic"],
        "similarityBps": result["similarityBps"],
        "thresholdBps": result["thresholdBps"],
        "branches": result["branches"],
        "attestation": attestation
    }
    if "pointsPassed" in result:
        response_payload["pointsPassed"] = result["pointsPassed"]
        response_payload["totalPoints"] = result["totalPoints"]
        response_payload["pointBreakdown"] = result["pointBreakdown"]
        response_payload["requiredPoints"] = result.get("requiredPoints", 7)

    return response_payload

