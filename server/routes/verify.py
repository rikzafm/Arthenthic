import json
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from server.crypto.sun import sun_verifier
from server.crypto.attestation import attestation_signer
from server.ml.embedder import EXTRACTOR_VERSION
from server.ml.similarity import similarity_engine
from server.storage import store
from server.db.database import get_db
from server.db.models import Artwork, NfcChip, ProvenanceEventModel, CaptureRecord, User
from server.db.redis_hotpath import redis_hotpath
from server.paymaster.policy_engine import paymaster_engine

router = APIRouter(prefix="/v1/verify", tags=["verify"])

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "").strip()
    session = store.sessions.get(token)
    if session:
        return session
    try:
        from server.auth.tokens import decode_access_token
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first() if user_id else None
        wallet_addr = (user.wallets[0].address if (user and getattr(user, "wallets", None)) else getattr(user, "email", user_id)) if user else user_id
        return {
            "address": wallet_addr or "0x0000000000000000000000000000000000000000",
            "roles": payload.get("roles", ["Collector"]),
            "email": getattr(user, "email", None) if user else None,
        }
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

def get_optional_verify_user(
    authorization: Optional[str] = Header(None),
    db: DBSession = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None
    return get_current_user(authorization=authorization, db=db)

class SunParams(BaseModel):
    uid: str
    ctr: int
    cmac: str
    tamperStatus: Optional[str] = "TAMPER_OK"

class Level1Request(BaseModel):
    sunParams: SunParams
    tokenId: Optional[str] = "101"

class Level2Request(BaseModel):
    tokenId: str
    captureId: Optional[str] = None
    captureIds: Optional[List[str]] = None
    extractorVersion: str = EXTRACTOR_VERSION
    sunParams: Optional[SunParams] = None

class PublicGuestVerifyRequest(BaseModel):
    uid: str
    ctr: int
    cmac: str
    tamperStatus: Optional[str] = "TAMPER_OK"

class CalibrateSubstrateRequest(BaseModel):
    substrate: str = "LINEN_CANVAS"
    ambient_lux: float = 500.0
    measured_roughness_mm: float = 0.45
    photo_texture_score: float = 90.0

@router.post("/calibrate-substrate")
def calibrate_substrate_endpoint(req: CalibrateSubstrateRequest):
    """
    Evaluates field sensor calibration against artwork substrate profiles
    (LINEN_CANVAS, WOOD_PANEL, IMPASTO_OIL, WATERCOLOR_COTTON).
    Returns recommended threshold bps, calibrated score, and authenticity pass/fail.
    """
    from server.ml.calibration import substrate_engine
    eval_result = substrate_engine.evaluate_substrate_calibration(
        substrate=req.substrate,
        depth_roughness_mm=req.measured_roughness_mm,
        photo_texture_pct=req.photo_texture_score,
        ambient_lux=req.ambient_lux,
    )
    return {
        "substrate": eval_result["substrate"],
        "display_name": eval_result["display_name"],
        "is_valid_substrate": True,
        "recommended_threshold_bps": eval_result["thresholdBps"],
        "calibrated_score_bps": eval_result["similarityBps"],
        "is_authentic": eval_result["isAuthentic"],
        "flat_print_passed": eval_result["flatPrintPassed"],
        "ambient_lux": req.ambient_lux,
        "measured_roughness_mm": req.measured_roughness_mm,
    }

@router.get("/simulate-sun")
def get_simulated_sun_params(uid: str = "04A1B2C3D4E5F6"):
    """
    Debug helper: Issues valid next simulated SUN parameters (incremented counter + CMAC).
    """
    return sun_verifier.generate_sun_params(uid)

@router.post("/public")
def verify_public_nfc_guest(
    req: PublicGuestVerifyRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    """
    D-14* Zero-Install Public NFC Tap Web Viewer.
    Tapping NTAG 424 DNA tag opens verify.arthentic.io in mobile browser without app.
    Rate-limited via Redis sliding-window (Key #4: rl:verify:{ipHash}).
    Returns L1 Authenticity Result (D-09) and D-15* Status Badge.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    ok, count = redis_hotpath.check_rate_limit(client_ip, max_requests=60, window_seconds=60)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many verification requests. Please wait 1 minute."}}
        )

    # Database lookup of NFC chip
    chip = db.query(NfcChip).filter(func.lower(NfcChip.chip_uid) == req.uid.lower()).first()
    if not chip or not chip.is_active or chip.token_id is None:
        raise HTTPException(status_code=404, detail="NFC Chip not found or not enrolled")

    # Linked artwork lookup
    artwork = db.query(Artwork).filter(Artwork.token_id == chip.token_id).first()
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found")

    # 1. Cryptographic CMAC and tamper-loop check before advancing monotonic counter
    if str(req.tamperStatus or "TAMPER_OK").upper() == "TAMPER_PERM_OPEN":
        return {
            "status": "COMPROMISED",
            "level": 1,
            "uid": req.uid,
            "ctr": req.ctr,
            "sunDigest": "0x" + "0" * 64,
            "statusBadge": "FLAGGED",
            "tamperDetected": True,
            "title": artwork.title,
            "artist": artwork.artist_name,
            "coaUrl": f"/v1/genesis/coa/{artwork.token_id}",
            "deepLink": f"arthentic://scan/{artwork.token_id}?uid={req.uid}&ctr={req.ctr}",
            "message": "Physical tamper loop broken. Tag has been severed or tampered with.",
        }

    expected_cmac = sun_verifier.compute_cmac(req.uid, req.ctr)
    if req.cmac.upper() != expected_cmac.upper():
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_CMAC_INVALID", "message": "Invalid CMAC: cryptographic tag verification failed"}}
        )

    # 2. Hot-path Redis monotonic counter check (Key #1 / D-02)
    ctr_ok, ctr_err = redis_hotpath.check_and_update_sun_counter(req.uid, req.ctr)
    if not ctr_ok:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_REPLAY_DETECTED", "message": ctr_err}}
        )

    valid, err, _ = sun_verifier.verify_sun_with_tamper(
        req.uid, req.ctr, req.cmac, req.tamperStatus or "TAMPER_OK"
    )
    if not valid:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_REPLAY_DETECTED", "message": err}}
        )

    sun_digest = attestation_signer.compute_sun_digest(req.uid, req.ctr, req.cmac)

    return {
        "status": "VALID",
        "level": 1,
        "uid": req.uid,
        "ctr": req.ctr,
        "sunDigest": sun_digest,
        "statusBadge": artwork.status or "CLEAR",
        "title": artwork.title,
        "artist": artwork.artist_name,
        "coaUrl": f"/v1/genesis/coa/{artwork.token_id}",
        "deepLink": f"arthentic://scan/{artwork.token_id}?uid={req.uid}&ctr={req.ctr}",
        "message": "Authentic physical NTAG 424 DNA tag verified. Open Arthentic iOS App for 3D LiDAR scan.",
    }

@router.post("/level1")
def verify_level1(
    req: Level1Request,
    user: Optional[Dict[str, Any]] = Depends(get_optional_verify_user),
    db: DBSession = Depends(get_db),
):
    """
    Level 1: Tap NFC chip (SUN cryptographic verification)
    Checks SUN authenticity, rejects counter replays via Redis hot-path Key #1,
    and returns signed EIP-712 attestation.
    """
    token_int = int(req.tokenId) if (req.tokenId and req.tokenId.isdigit()) else None
    if token_int is None:
        raise HTTPException(status_code=404, detail="Artwork or NFC chip not found")

    artwork = db.query(Artwork).filter(Artwork.token_id == token_int).first()
    chip = (
        db.query(NfcChip)
        .filter(
            func.lower(NfcChip.chip_uid) == req.sunParams.uid.lower(),
            NfcChip.token_id == token_int,
            NfcChip.is_active.is_(True),
        )
        .first()
    )
    if not artwork or not chip:
        raise HTTPException(status_code=404, detail="Artwork or NFC chip not found")

    # 1. Tamper loop and CMAC check before advancing monotonic counter
    if str(req.sunParams.tamperStatus or "TAMPER_OK").upper() == "TAMPER_PERM_OPEN":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "TAMPER_LOOP_SEVERED",
                    "message": "Tamper loop permanently opened: physical chip compromise detected",
                    "tamperDetected": True,
                }
            },
        )

    expected_cmac = sun_verifier.compute_cmac(req.sunParams.uid, req.sunParams.ctr)
    if req.sunParams.cmac.upper() != expected_cmac.upper():
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_VERIFICATION_FAILED", "message": "Invalid CMAC: cryptographic tag verification failed"}}
        )

    # 2. Redis hot-path monotonic counter check (Key #1 / D-02)
    ctr_ok, ctr_err = redis_hotpath.check_and_update_sun_counter(req.sunParams.uid, req.sunParams.ctr)
    if not ctr_ok:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_REPLAY_DETECTED", "message": ctr_err}}
        )

    valid, err, _ = sun_verifier.verify_sun_with_tamper(
        req.sunParams.uid,
        req.sunParams.ctr,
        req.sunParams.cmac,
        req.sunParams.tamperStatus or "TAMPER_OK",
    )
    if not valid:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "SUN_REPLAY_DETECTED", "message": err}}
        )

    sun_digest = attestation_signer.compute_sun_digest(
        req.sunParams.uid,
        req.sunParams.ctr,
        req.sunParams.cmac
    )

    attestation = attestation_signer.create_attestation(
        token_id=token_int,
        sun_digest=sun_digest,
        similarity_bps=0 # Level 1 chip verification
    )

    # Paymaster policy check for Tier T3 (K-01 / K-02)
    user_addr = user.get("address", "0x0000000000000000000000000000000000000000") if user else "0x0000000000000000000000000000000000000000"
    user_roles = user.get("roles", ["Guest"]) if user else ["Guest"]
    sponsorship = paymaster_engine.evaluate_sponsorship(
        wallet_address=user_addr,
        method_name="verifyLevel1",
        user_roles=user_roles,
    )

    prov_event = ProvenanceEventModel(
        token_id=token_int,
        event_type="LEVEL1_VERIFICATION",
        actor=user_addr if user_addr != "0x0000000000000000000000000000000000000000" else "Guest",
        role=user_roles[0] if user_roles else "Guest",
        details=f"NFC SUN chip verified (uid: {req.sunParams.uid}, ctr: {req.sunParams.ctr})"
    )
    db.add(prov_event)
    db.commit()

    return {
        "status": "VALID",
        "level": 1,
        "ctr": req.sunParams.ctr,
        "statusBadge": artwork.status or "CLEAR",
        "attestation": attestation,
        "sponsorship": sponsorship,
    }

@router.post("/level2")
def verify_level2(
    req: Level2Request,
    user: Optional[Dict[str, Any]] = Depends(get_optional_verify_user),
    db: DBSession = Depends(get_db),
):
    """
    Level 2: Camera + LiDAR surface fingerprint matching against genesis baseline.
    Supports single-point capture or 8-point spatial grid verification.
    """
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

    token_int = int(req.tokenId) if (req.tokenId and req.tokenId.isdigit()) else None
    artwork = db.query(Artwork).filter(Artwork.token_id == token_int).first() if token_int is not None else None
    if not artwork:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ARTWORK_NOT_FOUND", "message": f"Artwork {req.tokenId} not found"}}
        )

    capture_ids = req.captureIds if req.captureIds else ([req.captureId] if req.captureId else [])
    if not capture_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NO_CAPTURES", "message": "Either captureId or captureIds must be provided"}}
        )

    captures = []
    for cid in capture_ids:
        cap_record = db.query(CaptureRecord).filter(CaptureRecord.id == cid).first()
        if not cap_record:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "CAPTURE_NOT_FOUND", "message": f"Capture {cid} not found"}}
            )
        cap = {
            "id": cap_record.id,
            "vector": cap_record.vector,
            "depth_stats": cap_record.depth_stats or {
                "relief_roughness": cap_record.relief_roughness,
                "flat_print_passed": cap_record.flat_print_passed,
            },
            "metadata": cap_record.metadata_payload or {"pointIndex": cap_record.point_index or 1},
        }
        captures.append(cap)

    is_multi_point = len(captures) > 1 or (bool(artwork.genesis_points) and len(captures) > 1)
    if is_multi_point:
        verify_points = []
        for idx, cap in enumerate(captures):
            pt_idx = cap.get("metadata", {}).get("pointIndex", idx + 1)
            verify_points.append({
                "pointIndex": pt_idx,
                "vector": cap["vector"],
                "depth_stats": cap["depth_stats"]
            })

        genesis_points = artwork.genesis_points or [{
            "pointIndex": 1,
            "vector": artwork.genesis_vector,
            "depth_stats": artwork.genesis_depth
        }]

        result = similarity_engine.compare_multipoint(genesis_points, verify_points)
    else:
        capture = captures[0]
        genesis_vec = artwork.genesis_vector
        verify_vec = capture["vector"]
        genesis_depth = artwork.genesis_depth
        verify_depth = capture["depth_stats"]
        result = similarity_engine.compare(genesis_vec, verify_vec, genesis_depth, verify_depth)

    if req.sunParams:
        sun_digest = attestation_signer.compute_sun_digest(
            req.sunParams.uid, req.sunParams.ctr, req.sunParams.cmac
        )
    else:
        sun_digest = "0x" + "0" * 64

    attestation = attestation_signer.create_attestation(
        token_id=token_int,
        sun_digest=sun_digest,
        similarity_bps=result["similarityBps"]
    )

    user_addr = user.get("address", "0x0000000000000000000000000000000000000000") if user else "0x0000000000000000000000000000000000000000"
    user_roles = user.get("roles", ["Guest"]) if user else ["Guest"]
    sponsorship = paymaster_engine.evaluate_sponsorship(
        wallet_address=user_addr,
        method_name="recordVerification",
        user_roles=user_roles,
    )

    status_badge = "CLEAR" if result["isAuthentic"] else "FLAGGED"

    pass_details = f"Points passed: {result.get('pointsPassed', 1)}/{result.get('totalPoints', 1)}" if is_multi_point else ""
    prov_event = ProvenanceEventModel(
        token_id=token_int,
        event_type="LEVEL2_VERIFICATION",
        actor=user_addr if user_addr != "0x0000000000000000000000000000000000000000" else "Guest",
        role=user_roles[0] if user_roles else "Guest",
        details=f"Surface fingerprint scan {'AUTHENTIC' if result['isAuthentic'] else 'FAILED'}: {result['similarityBps'] / 100:.1f}% similarity. {pass_details}".strip(),
    )
    db.add(prov_event)
    db.commit()

    response_payload = {
        "isAuthentic": result["isAuthentic"],
        "similarityBps": result["similarityBps"],
        "thresholdBps": result["thresholdBps"],
        "statusBadge": status_badge,
        "branches": result["branches"],
        "attestation": attestation,
        "sponsorship": sponsorship,
    }
    if "pointsPassed" in result:
        response_payload["pointsPassed"] = result["pointsPassed"]
        response_payload["totalPoints"] = result["totalPoints"]
        response_payload["pointBreakdown"] = result["pointBreakdown"]
        response_payload["requiredPoints"] = result.get("requiredPoints", 7)

    return response_payload

