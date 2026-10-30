"""
server/tests/conftest.py
Global pytest test fixtures for Arthentic backend test suites.
Initializes database schema, seeds dev users, standard development Artwork(token_id=101)
with valid 384-d normalized vector and 8-point baseline grid, and binds NfcChip.
"""

import hashlib
import time
import pytest
import numpy as np
from datetime import datetime, timezone
from sqlalchemy import text

from server.db.database import Base, engine, SessionLocal
from server.db.models import Artwork, NfcChip, ProvenanceEventModel, CaptureRecord
from server.db.seed import seed_dev_users


def ensure_schema_columns(engine):
    """Ensures all columns exist in local SQLite/PostgreSQL development database."""
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            # Check artworks columns
            result = conn.execute(text("PRAGMA table_info(artworks)")).fetchall()
            col_names = {row[1] for row in result}
            if col_names:
                if "genesis_vector" not in col_names:
                    conn.execute(text("ALTER TABLE artworks ADD COLUMN genesis_vector JSON"))
                if "genesis_depth" not in col_names:
                    conn.execute(text("ALTER TABLE artworks ADD COLUMN genesis_depth JSON"))
                if "genesis_points" not in col_names:
                    conn.execute(text("ALTER TABLE artworks ADD COLUMN genesis_points JSON"))

            # Check capture_records columns
            result = conn.execute(text("PRAGMA table_info(capture_records)")).fetchall()
            cap_col_names = {row[1] for row in result}
            if cap_col_names:
                if "vector" not in cap_col_names:
                    conn.execute(text("ALTER TABLE capture_records ADD COLUMN vector JSON"))
                if "depth_stats" not in cap_col_names:
                    conn.execute(text("ALTER TABLE capture_records ADD COLUMN depth_stats JSON"))
                if "intrinsics" not in cap_col_names:
                    conn.execute(text("ALTER TABLE capture_records ADD COLUMN intrinsics JSON"))
                if "metadata_payload" not in cap_col_names:
                    conn.execute(text("ALTER TABLE capture_records ADD COLUMN metadata_payload JSON"))
            conn.commit()
    except Exception:
        pass


def seed_standard_development_artwork():
    """Seeds standard token 101 Artwork, bound NfcChip, and baseline provenance events."""
    ensure_schema_columns(engine)
    seed_dev_users()

    db = SessionLocal()
    try:
        # Check if artwork 101 already exists
        artwork = db.query(Artwork).filter(Artwork.token_id == 101).first()

        # Valid 384-dim normalized genesis vector
        v = np.ones(384, dtype=np.float32)
        v = v / np.linalg.norm(v)
        v_list = v.tolist()
        vector_hash = "0x" + hashlib.sha256(v.tobytes()).hexdigest()
        chip_id_hash = "0x4a8c91d8ef324701982bfe124"
        chip_uid = "04A1B2C3D4E580"

        # 8 baseline spatial points for the canvas
        points = []
        for i in range(1, 9):
            np.random.seed(i * 100)
            pv = np.ones(384, dtype=np.float32) + np.random.normal(0, 0.05, 384).astype(np.float32)
            pv = pv / np.linalg.norm(pv)
            points.append({
                "pointIndex": i,
                "vector": pv.tolist(),
                "depth_stats": {"relief_roughness": 0.45, "flat_print_passed": True}
            })

        if not artwork:
            artwork = Artwork(
                token_id=101,
                title="Study in Blue and Gold",
                artist_name="Elena Vance",
                artist_wallet="0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                owner_wallet="0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                medium="Oil on Belgian linen",
                dimensions="120 x 95 cm",
                year=2024,
                genesis_vector_hash=vector_hash,
                chip_id_hash=chip_id_hash,
                genesis_vector=v_list,
                genesis_depth={"relief_roughness": 0.48, "flat_print_passed": True},
                genesis_points=points,
                status="CLEAR",
                onchain_tx_hash="0x9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e",
            )
            db.add(artwork)
        else:
            artwork.status = "CLEAR"
            if not artwork.genesis_vector:
                artwork.genesis_vector = v_list
            if not artwork.genesis_depth:
                artwork.genesis_depth = {"relief_roughness": 0.48, "flat_print_passed": True}
            if not artwork.genesis_points:
                artwork.genesis_points = points

        # Seed / bind standard NFC chips (both uppercase and lowercase variations)
        for uid in ["04A1B2C3D4E580", "04A1B2C3D4E5F6", "04a1b2c3d4e5f6", "04a1b2c3d4e580"]:
            chip = db.query(NfcChip).filter(NfcChip.chip_uid == uid).first()
            if not chip:
                chip = NfcChip(
                    chip_uid=uid,
                    chip_id_hash="0x" + hashlib.sha256(uid.encode("utf-8")).hexdigest(),
                    token_id=101,
                    key_ref=f"arn:aws:kms:arthentic:key/{uid}",
                    is_active=True,
                )
                db.add(chip)
            else:
                if chip.token_id != 101:
                    chip.token_id = 101
                if not chip.is_active:
                    chip.is_active = True

        # Seed standard capture records for token 101 points
        for i in range(1, 9):
            cid = f"cap_101_pt{i}"
            cap = db.query(CaptureRecord).filter(CaptureRecord.id == cid).first()
            pv = points[i - 1]["vector"]
            if not cap:
                cap = CaptureRecord(
                    id=cid,
                    token_id=101,
                    point_index=i,
                    vector_hash="0x" + hashlib.sha256(np.array(pv, dtype=np.float32).tobytes()).hexdigest(),
                    relief_roughness=0.48,
                    flat_print_passed=True,
                    has_lidar=True,
                    vector=pv,
                    depth_stats={"relief_roughness": 0.48, "flat_print_passed": True},
                    intrinsics={"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0},
                    metadata_payload={"pointIndex": i, "distanceCm": 14, "steadiness": "Good"},
                )
                db.add(cap)

        for i in range(1, 6):
            cid = f"cap_pt{i}"
            cap = db.query(CaptureRecord).filter(CaptureRecord.id == cid).first()
            pv = points[(i - 1) % len(points)]["vector"]
            if not cap:
                cap = CaptureRecord(
                    id=cid,
                    token_id=101,
                    point_index=i,
                    vector_hash="0x" + hashlib.sha256(np.array(pv, dtype=np.float32).tobytes()).hexdigest(),
                    relief_roughness=0.48,
                    flat_print_passed=True,
                    has_lidar=True,
                    vector=pv,
                    depth_stats={"relief_roughness": 0.48, "flat_print_passed": True},
                    intrinsics={"fx": 1420.5, "fy": 1420.5, "cx": 64.0, "cy": 64.0},
                    metadata_payload={"pointIndex": i, "distanceCm": 14, "steadiness": "Good"},
                )
                db.add(cap)

        # Seed provenance events for token 101 if none exist
        prov_count = db.query(ProvenanceEventModel).filter(ProvenanceEventModel.token_id == 101).count()
        if prov_count == 0:
            db.add(ProvenanceEventModel(
                token_id=101,
                event_type="GENESIS_ENROLLMENT",
                actor="0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                role="Conservator",
                details="Genesis canvas scan enrolled (8 points captured)",
            ))
            db.add(ProvenanceEventModel(
                token_id=101,
                event_type="LEVEL1_VERIFICATION",
                actor="0x7a3f1b2c9e44d0a85b6c3f7e21c9c91d",
                role="Collector",
                details="NFC SUN tap verified (ctr 65)",
            ))

        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="function", autouse=True)
def setup_test_database():
    """Initializes schema and seeds standard test fixtures for each test."""
    seed_standard_development_artwork()
    yield
