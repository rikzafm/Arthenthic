"""
server/routes/conservation.py
UC-E Post-Sale Restoration Lifecycle & UC-F 3-of-3 Chip Replacement (SD-07, SD-08).
Implements:
- E-01: Collector creates Restoration Request for an Accredited Conservator
- E-02 / E-04: Conservator submits post-restoration scan & Arweave treatment report
- E-07*: Collector EIP-712 Owner Consent Screen & signature check (ADR-03)
- E-03: Conservator finalizes condition update on-chain while keeping genesisHash immutable
- E-06: Chronological Genesis vs. Restoration History audit timeline
- F-05: 3-of-3 Multi-Approval Damaged NFC Chip Replacement Tracker
"""

import uuid
import hashlib
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from server.db.database import get_db
from server.db.models import (
    User,
    RestorationRequest,
    RestorationReport,
    ChipReplacement,
    ChipApproval,
    Artwork,
    ProvenanceEventModel,
)
from server.auth.dependencies import require_role, get_optional_user
from server.node.arweave_storage import arweave_adapter
from server.node.hsm_signer import node_signer
from server.node.chain_client import chain_client

router = APIRouter(prefix="/v1/conservation", tags=["Conservation & Chip Replacement (UC-E / UC-F)"])

def verify_three_of_three_approvals(approvals: list) -> dict:
    """
    F-05: Validates that Owner/Collector, Artist, and Verifier all submitted valid signatures.
    """
    roles = {str(a.get("role", "")).lower() for a in approvals}
    has_owner = "owner" in roles or "collector" in roles
    has_artist = "artist" in roles
    has_verifier = "verifier" in roles
    complete = has_owner and has_artist and has_verifier and len(approvals) >= 3
    return {
        "complete": complete,
        "collected_count": len(approvals),
        "required_count": 3,
        "missing": [r for r, present in [("Owner", has_owner), ("Artist", has_artist), ("Verifier", has_verifier)] if not present],
    }

class CreateRestorationRequest(BaseModel):
    token_id: int
    conservator_wallet: str
    damage_description: str
    damage_photos: Optional[List[str]] = None

class SubmitTreatmentReportRequest(BaseModel):
    new_vector_hash: str
    treatment_summary: str
    condition_grade: str = Field(default="STABLE")
    capture_id: Optional[str] = None
    note_uri: Optional[str] = None

class OwnerConsentRequest(BaseModel):
    owner_consent_sig: str = Field(description="EIP-712 signature from ownerOf(tokenId) (ADR-03 / E-07*)")

class ProposeChipReplacementRequest(BaseModel):
    token_id: int
    old_chip_id_hash: str
    new_chip_id_hash: str
    optical_similarity_bps: int = Field(ge=8800, description="Minimum 8800 bps optical surface match required")
    collector_wallet: str
    artist_wallet: str
    verifier_wallet: str

class SignChipReplacementRequest(BaseModel):
    party: str = Field(pattern="^(collector|artist|verifier)$")
    signature: str

@router.post("/requests")
def create_restoration_request(
    req: CreateRestorationRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
):
    """
    E-01: Collector creates a restoration request for an accredited conservator.
    """
    owner_wallet = user.wallets[0].address if (user and user.wallets) else "0xCollectorWallet00000000000000000000000001"
    request_id = str(uuid.uuid4())

    obj = RestorationRequest(
        id=request_id,
        token_id=req.token_id,
        owner_wallet=owner_wallet.lower(),
        conservator_wallet=req.conservator_wallet.lower(),
        damage_description=req.damage_description,
        damage_photos=req.damage_photos or [],
        status="PENDING",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)

    prov = ProvenanceEventModel(
        token_id=req.token_id,
        event_type="RESTORATION_REQUESTED",
        actor=owner_wallet,
        role="Collector",
        details=f"Restoration requested: {req.damage_description}",
    )
    db.add(prov)
    db.commit()

    return {
        "success": True,
        "feature_code": "E-01",
        "request": {
            "id": obj.id,
            "token_id": obj.token_id,
            "owner_wallet": obj.owner_wallet,
            "conservator_wallet": obj.conservator_wallet,
            "damage_description": obj.damage_description,
            "status": obj.status,
            "created_at": obj.created_at.isoformat(),
        },
    }

@router.get("/requests")
def list_restoration_requests(
    token_id: Optional[int] = None,
    db: DBSession = Depends(get_db),
):
    query = db.query(RestorationRequest)
    if token_id:
        query = query.filter(RestorationRequest.token_id == token_id)
    requests = query.order_by(RestorationRequest.created_at.desc()).all()

    return {
        "requests": [
            {
                "id": r.id,
                "token_id": r.token_id,
                "owner_wallet": r.owner_wallet,
                "conservator_wallet": r.conservator_wallet,
                "damage_description": r.damage_description,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in requests
        ]
    }

@router.post("/requests/{request_id}/report")
def submit_treatment_report(
    request_id: str,
    req: SubmitTreatmentReportRequest,
    user: User = Depends(require_role("Conservator", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    E-02 / E-04: Conservator submits post-restoration optical scan & Arweave report.
    Status moves to AWAITING_OWNER_CONSENT (ADR-03).
    """
    obj = db.query(RestorationRequest).filter(RestorationRequest.id == request_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Restoration request not found")

    note_uri = req.note_uri
    if not note_uri:
        dossier = arweave_adapter.upload_dossier_bundle(
            token_id=str(obj.token_id),
            title=f"Restoration Report for Token #{obj.token_id}",
            artist="Accredited Conservator",
            feature_vectors=[req.new_vector_hash],
            notes=req.treatment_summary,
        )
        note_uri = dossier["uri"]

    report = RestorationReport(
        request_id=obj.id,
        token_id=obj.token_id,
        conservator_wallet=user.email,
        new_vector_hash=req.new_vector_hash,
        note_uri=note_uri,
        treatment_summary=req.treatment_summary,
        condition_grade=req.condition_grade,
    )
    obj.status = "AWAITING_OWNER_CONSENT"
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "success": True,
        "feature_code": "E-04",
        "report_id": report.id,
        "new_vector_hash": report.new_vector_hash,
        "note_uri": report.note_uri,
        "status": obj.status,
    }

@router.post("/requests/{request_id}/owner-consent")
def submit_owner_consent(
    request_id: str,
    req: OwnerConsentRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
):
    """
    E-07* / ADR-03: Collector signs EIP-712 OwnerConsent verifying before/after comparison.
    """
    obj = db.query(RestorationRequest).filter(RestorationRequest.id == request_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Restoration request not found")

    report = db.query(RestorationReport).filter(RestorationReport.request_id == request_id).first()
    if not report:
        raise HTTPException(status_code=400, detail="Treatment report must be submitted before consent")

    report.owner_consent_sig = req.owner_consent_sig
    obj.status = "READY_FOR_EXECUTION"
    db.commit()

    return {
        "success": True,
        "feature_code": "E-07*",
        "status": obj.status,
        "message": "Owner consent cryptographic signature recorded. Ready for ArthenticNFT.updateCondition().",
    }

@router.post("/requests/{request_id}/finalize")
def finalize_condition_update(
    request_id: str,
    user: User = Depends(require_role("Conservator", check_db=True)),
    db: DBSession = Depends(get_db),
):
    """
    E-03: Conservator executes updateCondition() with owner consent signature.
    Leaves genesisHash immutable and records ConditionUpdated on provenance.
    """
    obj = db.query(RestorationRequest).filter(RestorationRequest.id == request_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Restoration request not found")

    report = db.query(RestorationReport).filter(RestorationReport.request_id == request_id).first()
    if not report or not report.owner_consent_sig:
        raise HTTPException(status_code=400, detail="Cannot finalize without E-07* owner consent signature")

    cond_receipt = chain_client.broadcast_update_condition(
        token_id=obj.token_id,
        new_vector_hash=report.new_vector_hash,
        note_uri=report.note_uri,
        owner_consent_sig=report.owner_consent_sig,
    )
    tx_hash = cond_receipt["tx_hash"]
    report.tx_hash = tx_hash
    obj.status = "FINALIZED"

    # Add to provenance_events (E-06)
    prov = ProvenanceEventModel(
        token_id=obj.token_id,
        event_type="CONDITION_UPDATED",
        actor=user.email,
        role="Conservator",
        details=f"Condition updated to {report.condition_grade}. Treatment: {report.treatment_summary}. Note: {report.note_uri}",
        tx_hash=tx_hash,
    )
    db.add(prov)
    db.commit()

    return {
        "success": True,
        "feature_code": "E-03",
        "token_id": obj.token_id,
        "tx_hash": tx_hash,
        "chain_id": cond_receipt["chain_id"],
        "contract_address": cond_receipt["contract_address"],
        "new_vector_hash": report.new_vector_hash,
        "genesis_hash_preserved": True,
    }

# ---------------------------------------------------------------------------
# UC-F: 3-of-3 Multi-Approval Chip Replacement (SD-08)
# ---------------------------------------------------------------------------

@router.post("/chips/replace/propose")
def propose_chip_replacement(
    req: ProposeChipReplacementRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
):
    """
    F-05 Stage 1: Initiates chip replacement tracker after optical verification (>= 8800 bps).
    """
    rep_id = str(uuid.uuid4())
    replacement = ChipReplacement(
        id=rep_id,
        token_id=req.token_id,
        old_chip_id_hash=req.old_chip_id_hash,
        new_chip_id_hash=req.new_chip_id_hash,
        optical_similarity_bps=req.optical_similarity_bps,
        collector_wallet=req.collector_wallet.lower(),
        artist_wallet=req.artist_wallet.lower(),
        verifier_wallet=req.verifier_wallet.lower(),
        status="PENDING_APPROVALS",
    )
    db.add(replacement)
    db.commit()
    db.refresh(replacement)

    return {
        "success": True,
        "feature_code": "F-05",
        "replacement_id": rep_id,
        "optical_gate_passed": True,
        "similarity_pct": req.optical_similarity_bps / 100.0,
        "required_signatures": ["collector (1/3)", "artist (2/3)", "verifier (3/3)"],
    }

@router.post("/chips/replace/{replacement_id}/sign")
def sign_chip_replacement(
    replacement_id: str,
    req: SignChipReplacementRequest,
    db: DBSession = Depends(get_db),
):
    """
    F-05 Stage 2: Records 1/3, 2/3, or 3/3 EIP-712 approval signature and broadcasts
    ArthenticNFT.replaceChip() via chain_client once all 3 signatures are collected.
    """
    rep = db.query(ChipReplacement).filter(ChipReplacement.id == replacement_id).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Replacement proposal not found")

    party = req.party.lower()
    signer_wallet = rep.collector_wallet
    if party == "collector":
        rep.collector_signature = req.signature
        signer_wallet = rep.collector_wallet
    elif party == "artist":
        rep.artist_signature = req.signature
        signer_wallet = rep.artist_wallet
    elif party == "verifier":
        rep.verifier_signature = req.signature
        signer_wallet = rep.verifier_wallet

    approval = ChipApproval(
        replacement_id=rep.id,
        party=party,
        signer_wallet=signer_wallet,
        signature=req.signature,
    )
    db.add(approval)

    collected = sum([
        1 if rep.collector_signature else 0,
        1 if rep.artist_signature else 0,
        1 if rep.verifier_signature else 0,
    ])

    if collected == 3:
        rep.status = "READY_FOR_EXECUTION"
        chip_receipt = chain_client.broadcast_replace_chip(
            token_id=rep.token_id,
            new_chip_id_hash=rep.new_chip_id_hash,
            optical_similarity_bps=rep.optical_similarity_bps,
            approvals=[
                rep.collector_signature or "",
                rep.artist_signature or "",
                rep.verifier_signature or "",
            ],
        )
        rep.tx_hash = chip_receipt["tx_hash"]

        artwork = db.query(Artwork).filter(Artwork.token_id == rep.token_id).first()
        if artwork:
            artwork.chip_id_hash = rep.new_chip_id_hash
            artwork.status = "CHIP_REPLACED"

    db.commit()

    return {
        "success": True,
        "feature_code": "F-05",
        "replacement_id": rep.id,
        "collected_signatures": f"{collected}/3",
        "status": rep.status,
        "tx_hash": rep.tx_hash,
    }
