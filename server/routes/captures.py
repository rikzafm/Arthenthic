import json
import uuid
import hashlib
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession

from server.ml.embedder import embedder
from server.ml.depth_features import depth_extractor
from server.db.database import get_db
from server.db.models import CaptureRecord
from server.routes.verify import get_current_user

router = APIRouter(prefix="/v1/captures", tags=["captures"])

@router.post("")
async def upload_capture(
    photo: UploadFile = File(...),
    depth: Optional[UploadFile] = File(None),
    intrinsics: str = Form(...),
    metadata: Optional[str] = Form("{}"),
    user: Dict[str, Any] = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Upload raw capture (photo + depth map + camera intrinsics + quality metadata).
    Server processes photo texture embedding and 3D depth relief statistics,
    and persists the record to the relational database (CaptureRecord).
    """
    capture_id = f"cap_{uuid.uuid4().hex[:12]}"

    photo_bytes = await photo.read()
    if len(photo_bytes) == 0:
        raise HTTPException(status_code=400, detail={"error": {"code": "EMPTY_PHOTO", "message": "Photo file is empty"}})

    # Extract photo embedding
    try:
        vector = embedder.extract_from_bytes(photo_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "PHOTO_PROCESSING_FAILED", "message": str(e)}}
        )

    # Parse intrinsics
    try:
        intrinsics_dict = json.loads(intrinsics)
    except Exception:
        intrinsics_dict = {"fx": 1400.0, "fy": 1400.0, "cx": 100.0, "cy": 100.0}

    # Depth processing
    if depth:
        depth_bytes = await depth.read()
        depth_stats = depth_extractor.extract_features(depth_bytes, intrinsics_dict)
    else:
        # Default fallback depth relief
        depth_stats = {"relief_roughness": 0.45, "flat_print_passed": True}

    try:
        meta_dict = json.loads(metadata)
    except Exception:
        meta_dict = {}

    vector_list = vector.tolist() if hasattr(vector, "tolist") else list(vector)
    vec_bytes = np.array(vector, dtype=np.float32).tobytes()
    vector_hash = "0x" + hashlib.sha256(vec_bytes).hexdigest()
    point_index = int(meta_dict.get("pointIndex", meta_dict.get("point_index", 1)))
    relief_roughness = float(depth_stats.get("relief_roughness", 0.45))
    flat_print_passed = bool(depth_stats.get("flat_print_passed", True))
    has_lidar = bool(depth is not None)

    record = CaptureRecord(
        id=capture_id,
        point_index=point_index,
        vector_hash=vector_hash,
        relief_roughness=relief_roughness,
        flat_print_passed=flat_print_passed,
        has_lidar=has_lidar,
        vector=vector_list,
        depth_stats=depth_stats,
        intrinsics=intrinsics_dict,
        metadata_payload=meta_dict,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {"captureId": capture_id}

