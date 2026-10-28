import json
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Optional, Dict, Any
from server.ml.embedder import embedder
from server.ml.depth_features import depth_extractor
from server.storage import store
from server.routes.verify import get_current_user

router = APIRouter(prefix="/v1/captures", tags=["captures"])

@router.post("")
async def upload_capture(
    photo: UploadFile = File(...),
    depth: Optional[UploadFile] = File(None),
    intrinsics: str = Form(...),
    metadata: Optional[str] = Form("{}"),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Upload raw capture (photo + depth map + camera intrinsics + quality metadata).
    Server processes photo texture embedding and 3D depth relief statistics.
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

    store.captures[capture_id] = {
        "captureId": capture_id,
        "vector": vector,
        "depth_stats": depth_stats,
        "intrinsics": intrinsics_dict,
        "metadata": meta_dict,
        "uploaded_by": user.get("address")
    }

    return {"captureId": capture_id}

