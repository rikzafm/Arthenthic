from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession

from server.db.database import get_db
from server.db.models import User, Artwork, ProvenanceEventModel
from server.auth.dependencies import require_role

router = APIRouter(prefix="/v1/gallery", tags=["gallery"])

class BatchVerifyItem(BaseModel):
    tokenId: str
    captureId: Optional[str] = None

class BatchVerifyRequest(BaseModel):
    items: List[BatchVerifyItem]

@router.post("/batch-verify")
def batch_verify(
    req: BatchVerifyRequest,
    user: User = Depends(require_role("Gallery", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    Bulk/batch verification for Gallery (Verifier) role.
    Mobile is read-only (signing stays on web).
    """
    results = []
    for item in req.items:
        token_int = int(item.tokenId) if item.tokenId.isdigit() else None
        artwork = db.query(Artwork).filter(Artwork.token_id == token_int).first() if token_int is not None else None
        status = "FOUND" if artwork else "NOT_FOUND"
        results.append({
            "tokenId": item.tokenId,
            "status": status,
            "title": artwork.title if artwork else None,
            "artist": artwork.artist_name if artwork else None,
            "verified": bool(artwork),
        })

    return {
        "status": "COMPLETED",
        "total": len(req.items),
        "results": results,
        "note": "Mobile is read-only. Multisig on-chain attestation must be signed on the Web portal.",
    }

@router.get("/reports")
def get_gallery_reports(
    user: User = Depends(require_role("Gallery", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    Verification reports for Gallery (Verifier) role.
    """
    reports = []
    artworks = db.query(Artwork).all()
    for artwork in artworks:
        event_count = db.query(ProvenanceEventModel).filter(ProvenanceEventModel.token_id == artwork.token_id).count()
        reports.append({
            "tokenId": str(artwork.token_id),
            "title": artwork.title,
            "artist": artwork.artist_name,
            "lastVerified": "Genesis Enrolled",
            "eventCount": event_count,
        })

    return {"reports": reports}
