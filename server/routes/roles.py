import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session as DBSession

from server.db.database import get_db
from server.db.models import User, AuditLog, RoleApplication, ApplicationDocument
from server.auth.dependencies import require_role
from server.auth.service import get_user_roles, normalize_role, create_audit_entry, VALID_ACCREDITED_ROLES
from server.auth.clock import get_current_time

router = APIRouter(prefix="/v1", tags=["roles_and_user"])

# In-memory store for user verification records
_user_verifications: Dict[str, List[Dict[str, Any]]] = {}

class ApplyRoleRequest(BaseModel):
    requested_role: str
    portfolio_url: Optional[str] = None
    bio_or_org: Optional[str] = None
    notes: Optional[str] = None
    documents: Optional[List[Dict[str, str]]] = None

class SaveVerificationRequest(BaseModel):
    tokenId: str
    level: int
    status: str
    attestation: Optional[Dict[str, Any]] = None

@router.post("/roles/apply")
def apply_for_role(
    req: ApplyRoleRequest,
    user: User = Depends(require_role("Collector", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    Apply for an accredited role (Artist, Gallery, Conservator).
    Available to Collectors. Guest cannot access.
    """
    target_role = normalize_role(req.requested_role)
    if target_role not in VALID_ACCREDITED_ROLES or target_role == "Admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_ROLE", "message": f"Cannot apply for role: {req.requested_role}"}}
        )

    current_roles = get_user_roles(db, user.id)
    if target_role in current_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "ALREADY_ACCREDITED", "message": f"User is already accredited as {target_role}."}}
        )

    # Check for existing pending application for this role
    pending = db.query(RoleApplication).filter(
        RoleApplication.user_id == user.id,
        RoleApplication.requested_role == target_role,
        RoleApplication.status == "pending",
    ).first()
    if pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "APPLICATION_PENDING", "message": f"You already have a pending application for {target_role}."}}
        )

    now = get_current_time()
    app_id = str(uuid.uuid4())
    payload = {
        "portfolio_url": req.portfolio_url,
        "bio_or_org": req.bio_or_org,
        "notes": req.notes,
    }

    application = RoleApplication(
        id=app_id,
        user_id=user.id,
        requested_role=target_role,
        status="pending",
        payload=payload,
        created_at=now,
    )
    db.add(application)

    # If documents provided
    doc_records = []
    if req.documents:
        for doc in req.documents:
            doc_id = str(uuid.uuid4())
            doc_obj = ApplicationDocument(
                id=doc_id,
                application_id=app_id,
                storage_key=doc.get("storage_key", f"docs/{app_id}/{doc_id}"),
                filename=doc.get("filename", "document.pdf"),
                mime=doc.get("mime", "application/pdf"),
                sha256=doc.get("sha256", hashlib.sha256(b"mock_doc").hexdigest()),
                created_at=now,
            )
            db.add(doc_obj)
            doc_records.append({
                "id": doc_id,
                "filename": doc_obj.filename,
                "storage_key": doc_obj.storage_key,
                "sha256": doc_obj.sha256,
            })

    create_audit_entry(
        db,
        action="ROLE_APPLICATION_SUBMITTED",
        actor_user_id=user.id,
        target_type="role_application",
        target_id=app_id,
        meta={"requested_role": target_role, "documents_count": len(doc_records)},
    )
    db.commit()
    db.refresh(application)

    return {
        "status": "submitted",
        "application": {
            "id": application.id,
            "user_id": application.user_id,
            "email": user.email,
            "requested_role": application.requested_role,
            "status": application.status,
            "payload": application.payload,
            "documents": doc_records,
            "created_at": application.created_at.isoformat() if application.created_at else None,
        }
    }

@router.post("/roles/apply/upload")
async def upload_application_document(
    file: UploadFile = File(...),
    user: User = Depends(require_role("Collector", check_db=True)),
):
    """
    Upload a supporting credential or accreditation document (ID, diploma, association letter).
    Computes SHA-256 and generates a secure storage key.
    """
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Uploaded document is empty."}}
        )

    file_hash = hashlib.sha256(content).hexdigest()
    doc_id = str(uuid.uuid4())
    storage_key = f"accreditation/{user.id}/{doc_id}_{file.filename}"

    return {
        "storage_key": storage_key,
        "filename": file.filename,
        "mime": file.content_type or "application/octet-stream",
        "sha256": file_hash,
        "size_bytes": len(content),
    }

@router.get("/roles/my-applications")
def get_my_applications(
    user: User = Depends(require_role("Collector", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    List role applications submitted by the current user with live status and reviewer feedback.
    """
    apps = db.query(RoleApplication).filter(RoleApplication.user_id == user.id).order_by(RoleApplication.created_at.desc()).all()
    results = []
    for a in apps:
        docs = [
            {
                "id": d.id,
                "filename": d.filename,
                "storage_key": d.storage_key,
                "mime": d.mime,
                "sha256": d.sha256,
            }
            for d in a.documents
        ]
        results.append({
            "id": a.id,
            "requested_role": a.requested_role,
            "status": a.status,
            "payload": a.payload,
            "documents": docs,
            "reviewed_by": a.reviewed_by,
            "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
            "review_note": a.review_note,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return {"applications": results}

@router.post("/user/verifications")
def save_verification_history(
    req: SaveVerificationRequest,
    user: User = Depends(require_role("Collector", "Artist", "Gallery", "Conservator", "Admin")),
):
    """
    Save verification history for authenticated user (Collector and above). Guest: 401.
    """
    if user.id not in _user_verifications:
        _user_verifications[user.id] = []

    record = {
        "tokenId": req.tokenId,
        "level": req.level,
        "status": req.status,
        "attestation": req.attestation,
        "verified_at": get_current_time().isoformat(),
        "user_id": user.id,
    }
    _user_verifications[user.id].append(record)
    return {"status": "saved", "record": record}

@router.get("/user/verifications")
def get_user_verifications(
    user: User = Depends(require_role("Collector", "Artist", "Gallery", "Conservator", "Admin")),
):
    """
    Get saved verification history.
    """
    return {"verifications": _user_verifications.get(user.id, [])}

@router.get("/user/artworks")
def get_user_artworks(
    user: User = Depends(require_role("Collector", "Artist", "Gallery", "Conservator", "Admin")),
):
    """
    Get artworks owned or registered by user.
    """
    return {
        "artworks": [
            {
                "tokenId": "101",
                "title": "Study in Indigo No. 4",
                "artist": "Elena Rostova",
                "lastVerified": "Today, 14:20",
                "owner_user_id": user.id,
            }
        ]
    }
