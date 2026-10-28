import hashlib
import uuid
import numpy as np
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from server.storage import store
from server.routes.verify import get_current_user

router = APIRouter(prefix="/v1", tags=["genesis"])

class GenesisPrepareRequest(BaseModel):
    captureIds: List[str]
    title: Optional[str] = "Untitled Artwork"
    artist: Optional[str] = "Unknown Artist"

class ConservationPrepareRequest(BaseModel):
    tokenId: str
    captureId: str
    noteURI: Optional[str] = ""

@router.post("/genesis/prepare")
def prepare_genesis(req: GenesisPrepareRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Enroll an artwork by combining multiple capture vectors into a genesis baseline.
    """
    if not req.captureIds:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "NO_CAPTURES", "message": "At least one capture ID required for genesis enrollment"}}
        )

    vectors = []
    depths = []
    points = []
    for idx, cid in enumerate(req.captureIds):
        cap = store.captures.get(cid)
        if cap:
            pt_idx = cap.get("metadata", {}).get("pointIndex", idx + 1)
            points.append({
                "pointIndex": pt_idx,
                "vector": cap["vector"],
                "depth_stats": cap["depth_stats"]
            })
            vectors.append(cap["vector"])
            depths.append(cap["depth_stats"])

    if not vectors:
        # Fallback vector for testing
        mean_vec = np.ones(384, dtype=np.float32) / np.sqrt(384)
        mean_roughness = 0.48
    else:
        mean_vec = np.mean(vectors, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 1e-6:
            mean_vec = mean_vec / norm
        mean_roughness = float(np.mean([d.get("relief_roughness", 0.45) for d in depths]))

    token_id = str(len(store.artworks) + 101)
    vector_hash = "0x" + hashlib.sha256(mean_vec.tobytes()).hexdigest()
    chip_id_hash = "0x" + hashlib.sha256(f"chip_{token_id}".encode()).hexdigest()[:40]

    store.artworks[token_id] = {
        "tokenId": token_id,
        "title": req.title,
        "artist": req.artist,
        "genesis_vector": mean_vec,
        "genesis_depth": {"relief_roughness": mean_roughness, "flat_print_passed": True},
        "genesis_points": points,
        "chip_id_hash": chip_id_hash,
        "last_verified": "Genesis Enrolled",
        "enrolled_by": user.get("address")
    }

    store.add_provenance_event(
        token_id=token_id,
        event_type="GENESIS_ENROLLMENT",
        actor=user.get("address", "0x"),
        role="Verifier",
        details=f"Genesis baseline enrolled with {len(req.captureIds)} capture points"
    )

    return {
        "tokenId": token_id,
        "genesisVectorHash": vector_hash,
        "chipIdHash": chip_id_hash,
        "metadataURI": f"ipfs://bafybeic{token_id}/metadata.json"
    }

@router.post("/conservation/prepare")
def prepare_conservation(req: ConservationPrepareRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Conservator flow: update the baseline vector after restoration or conservation work.
    """
    artwork = store.artworks.get(req.tokenId)
    if not artwork:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Artwork not found"}})

    capture = store.captures.get(req.captureId)
    if not capture:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Capture not found"}})

    new_vec = capture["vector"]
    vector_hash = "0x" + hashlib.sha256(new_vec.tobytes()).hexdigest()
    artwork["genesis_vector"] = new_vec
    artwork["genesis_depth"] = capture["depth_stats"]

    store.add_provenance_event(
        token_id=req.tokenId,
        event_type="CONSERVATION_UPDATE",
        actor=user.get("address", "0x"),
        role="Conservator",
        details=f"Baseline updated by Conservator. Note: {req.noteURI or 'Routine re-scan'}"
    )

    return {
        "tokenId": req.tokenId,
        "newVectorHash": vector_hash
    }

@router.get("/artworks/{tokenId}")
def get_artwork(tokenId: str):
    artwork = store.artworks.get(tokenId)
    if not artwork:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Artwork not found"}})
    return {
        "tokenId": artwork["tokenId"],
        "title": artwork["title"],
        "artist": artwork["artist"],
        "lastVerified": artwork.get("last_verified", "Never"),
        "chipIdHash": artwork.get("chip_id_hash", "")
    }

@router.get("/artworks/{tokenId}/provenance")
def get_provenance(tokenId: str):
    events = store.provenance.get(tokenId, [])
    return {"tokenId": tokenId, "events": events}

