"""
DEPRECATED: server.storage is deprecated as of Milestone 2 (Persistence & Storage Unification).
All route persistence has been migrated to SQLAlchemy database models (Artwork, CaptureRecord,
ProvenanceEventModel) and Redis hotpath.
This module remains as a temporary read-through compatibility shim for unmigrated components
and will be completely removed.
"""

import warnings
import time
import uuid
from typing import Dict, Any, Optional, List

warnings.warn(
    "server.storage is deprecated and will be removed. Use database models (Artwork, CaptureRecord, ProvenanceEventModel) instead.",
    DeprecationWarning,
    stacklevel=2,
)


class ArtworkProxyDict(dict):
    """Read-through dictionary proxy connecting to the database Artwork table."""

    def get(self, key, default=None):
        if super().__contains__(key):
            return super().get(key, default)
        try:
            from server.db.database import SessionLocal
            from server.db.models import Artwork
            token_int = int(key) if str(key).isdigit() else None
            if token_int is not None:
                with SessionLocal() as db:
                    art = db.query(Artwork).filter(Artwork.token_id == token_int).first()
                    if art:
                        return {
                            "tokenId": str(art.token_id),
                            "title": art.title,
                            "artist": art.artist_name,
                            "genesis_vector": art.genesis_vector,
                            "genesis_depth": art.genesis_depth,
                            "genesis_points": art.genesis_points or [],
                            "chip_id_hash": art.chip_id_hash,
                            "status": art.status,
                            "last_verified": "Genesis Enrolled",
                        }
        except Exception:
            pass
        return default

    def __getitem__(self, key):
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return self.get(key) is not None


class CaptureProxyDict(dict):
    """Read-through dictionary proxy connecting to the database CaptureRecord table."""

    def get(self, key, default=None):
        if super().__contains__(key):
            return super().get(key, default)
        try:
            from server.db.database import SessionLocal
            from server.db.models import CaptureRecord
            with SessionLocal() as db:
                cap = db.query(CaptureRecord).filter(CaptureRecord.id == str(key)).first()
                if cap:
                    return {
                        "captureId": cap.id,
                        "vector": cap.vector,
                        "depth_stats": cap.depth_stats or {
                            "relief_roughness": cap.relief_roughness,
                            "flat_print_passed": cap.flat_print_passed,
                        },
                        "intrinsics": cap.intrinsics or {},
                        "metadata": cap.metadata_payload or {"pointIndex": cap.point_index},
                    }
        except Exception:
            pass
        return default

    def __getitem__(self, key):
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        return self.get(key) is not None


class ProvenanceProxyDict(dict):
    """Read-through dictionary proxy connecting to the database ProvenanceEventModel table."""

    def get(self, key, default=None):
        if super().__contains__(key) and super().get(key):
            return super().get(key, default)
        try:
            from server.db.database import SessionLocal
            from server.db.models import ProvenanceEventModel
            token_int = int(key) if str(key).isdigit() else None
            if token_int is not None:
                with SessionLocal() as db:
                    events = (
                        db.query(ProvenanceEventModel)
                        .filter(ProvenanceEventModel.token_id == token_int)
                        .order_by(ProvenanceEventModel.created_at.asc())
                        .all()
                    )
                    if events:
                        return [
                            {
                                "type": ev.event_type,
                                "timestamp": ev.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.created_at else "",
                                "actor": ev.actor,
                                "role": ev.role,
                                "details": ev.details,
                            }
                            for ev in events
                        ]
        except Exception:
            pass
        return super().get(key, default)


class DataStore:
    def __init__(self):
        # session_token -> {address, roles, created_at}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # address -> active challenge nonce
        self.challenges: Dict[str, str] = {}
        # capture_id -> {photo_bytes, depth_bytes, intrinsics, metadata, vector, depth_stats}
        self.captures: Dict[str, Dict[str, Any]] = CaptureProxyDict()
        # token_id -> {title, artist, genesis_vector, genesis_depth, chip_id_hash, created_at}
        self.artworks: Dict[str, Dict[str, Any]] = ArtworkProxyDict()
        # token_id -> list of verification events
        self.provenance: Dict[str, List[Dict[str, Any]]] = ProvenanceProxyDict()

        self._seed_default_artwork()

    def _seed_default_artwork(self):
        """Seed initial demo artwork matching the prototype design"""
        import numpy as np
        token_id = "101"
        # Dummy normalized genesis vector
        v = np.ones(384, dtype=np.float32)
        v = v / np.linalg.norm(v)

        # Seed 8 baseline spatial points for the canvas
        points = []
        for i in range(1, 9):
            np.random.seed(i * 100)
            pv = np.ones(384, dtype=np.float32) + np.random.normal(0, 0.05, 384).astype(np.float32)
            pv = pv / np.linalg.norm(pv)
            points.append({
                "pointIndex": i,
                "vector": pv.tolist() if hasattr(pv, "tolist") else pv,
                "depth_stats": {"relief_roughness": 0.45, "flat_print_passed": True}
            })

        self.artworks[token_id] = {
            "tokenId": token_id,
            "title": "Study in Blue and Gold",
            "artist": "Elena Vance",
            "genesis_vector": v.tolist() if hasattr(v, "tolist") else v,
            "genesis_depth": {"relief_roughness": 0.48, "flat_print_passed": True},
            "genesis_points": points,
            "chip_id_hash": "0x4a8c91d8ef324701982bfe124",
            "last_verified": "2026-10-24 14:20 UTC",
            "created_at": time.time()
        }

        self.provenance[token_id] = [
            {
                "type": "GENESIS_ENROLLMENT",
                "timestamp": "2026-10-20T10:00:00Z",
                "actor": "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                "role": "Conservator",
                "details": "Genesis canvas scan enrolled (8 points captured)"
            },
            {
                "type": "LEVEL1_VERIFICATION",
                "timestamp": "2026-10-24T14:20:00Z",
                "actor": "0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                "role": "Collector",
                "details": "NFC SUN tap verified (ctr 65)"
            }
        ]

    def add_provenance_event(self, token_id: str, event_type: str, actor: str, role: str, details: str):
        if token_id not in self.provenance:
            self.provenance[token_id] = []
        self.provenance[token_id].append({
            "type": event_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor,
            "role": role,
            "details": details
        })
        try:
            from server.db.database import SessionLocal
            from server.db.models import ProvenanceEventModel
            token_int = int(token_id) if str(token_id).isdigit() else None
            if token_int is not None:
                with SessionLocal() as db:
                    m = ProvenanceEventModel(
                        token_id=token_int,
                        event_type=event_type,
                        actor=actor,
                        role=role,
                        details=details,
                    )
                    db.add(m)
                    db.commit()
        except Exception:
            pass

store = DataStore()
