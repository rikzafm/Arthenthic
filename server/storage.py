"""
In-memory and file-backed store for captures, genesis baselines, sessions, and provenance.
"""

import time
import uuid
from typing import Dict, Any, Optional, List

class DataStore:
    def __init__(self):
        # session_token -> {address, roles, created_at}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # address -> active challenge nonce
        self.challenges: Dict[str, str] = {}
        # capture_id -> {photo_bytes, depth_bytes, intrinsics, metadata, vector, depth_stats}
        self.captures: Dict[str, Dict[str, Any]] = {}
        # token_id -> {title, artist, genesis_vector, genesis_depth, chip_id_hash, created_at}
        self.artworks: Dict[str, Dict[str, Any]] = {}
        # token_id -> list of verification events
        self.provenance: Dict[str, List[Dict[str, Any]]] = {}

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
                "vector": pv,
                "depth_stats": {"relief_roughness": 0.45, "flat_print_passed": True}
            })

        self.artworks[token_id] = {
            "tokenId": token_id,
            "title": "Study in Blue and Gold",
            "artist": "Elena Vance",
            "genesis_vector": v,
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

store = DataStore()

