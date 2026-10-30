import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship, synonym
from server.db.database import Base

def utcnow():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

# ==============================================================================
# Domain 1 — Identity & Access (ERD 1)
# ==============================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    display_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="active")  # active, suspended, deleted
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    identities = relationship("AuthIdentity", back_populates="user", cascade="all, delete-orphan")
    role_assignments = relationship("RoleAssignment", back_populates="user", cascade="all, delete-orphan", foreign_keys="[RoleAssignment.user_id]")
    role_applications = relationship("RoleApplication", back_populates="user", cascade="all, delete-orphan", foreign_keys="[RoleApplication.user_id]")
    wallets = relationship("WalletLink", back_populates="user", cascade="all, delete-orphan")

class AuthIdentity(Base):
    __tablename__ = "auth_identities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)  # google, apple, metamask
    provider_subject = Column(String(255), nullable=False, index=True)
    email_at_link = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_provider_subject"),
    )

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    install_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    platform = Column(String(32), nullable=True)  # ios, android, web
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="devices")
    sessions = relationship("Session", back_populates="device")

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    absolute_expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    device = relationship("Device", back_populates="sessions")
    refresh_tokens = relationship("RefreshToken", back_populates="session", cascade="all, delete-orphan")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    family_id = Column(String(36), nullable=False, index=True)
    replaced_by = Column(String(36), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    session = relationship("Session", back_populates="refresh_tokens", foreign_keys=[session_id])

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    actor_user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(64), nullable=True)
    ip = Column(String(64), nullable=True)
    device_id = Column(String(64), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, index=True)  # artist, gallery, conservator, admin
    status = Column(String(32), nullable=False, default="active")  # active, revoked
    granted_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    granted_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    onchain_tx_hash = Column(String(66), nullable=True)

    user = relationship("User", back_populates="role_assignments", foreign_keys=[user_id])
    granter = relationship("User", foreign_keys=[granted_by])

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_role"),
    )

class RoleApplication(Base):
    __tablename__ = "role_applications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_role = Column(String(32), nullable=False, index=True)  # Artist, Gallery, Conservator
    status = Column(String(32), nullable=False, default="pending", index=True)  # pending, approved, rejected, more_info
    payload = Column(JSON, nullable=True)  # portfolio_url, notes, org_name, bio, etc.
    reviewed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="role_applications")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    documents = relationship("ApplicationDocument", back_populates="application", cascade="all, delete-orphan")

class ApplicationDocument(Base):
    __tablename__ = "application_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("role_applications.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=True)
    mime = Column(String(64), nullable=True)
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    application = relationship("RoleApplication", back_populates="documents")

class AccreditedProfile(Base):
    __tablename__ = "accredited_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, index=True)  # Artist, Gallery, Conservator
    display_name = Column(String(255), nullable=True)
    bio_or_org = Column(Text, nullable=True)
    website = Column(String(255), nullable=True)
    verification_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_profile_role"),
    )

class ActionToken(Base):
    __tablename__ = "action_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    purpose = Column(String(32), nullable=False, index=True)  # password_reset, email_verification
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])

class WalletLink(Base):
    __tablename__ = "wallet_links"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    address = Column(String(64), nullable=False, index=True)
    chain_id = Column(Integer, nullable=False, default=84532)  # 84532 = Base Sepolia, 8453 = Base Mainnet
    wallet_type = Column(String(32), nullable=False, default="metamask")  # metamask, eoa, smart_wallet, safe
    label = Column(String(128), nullable=True)
    passkey_credential_id = Column(String(255), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="wallets")

    __table_args__ = (
        UniqueConstraint("address", "chain_id", name="uq_wallet_address_chain"),
    )

# ==============================================================================
# Domain 2 — Artwork, Genesis & Chips (ERD 2)
# ==============================================================================

class Artwork(Base):
    __tablename__ = "artworks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, unique=True, nullable=True, index=True)
    title = Column(String(255), nullable=False)
    artist_name = Column(String(255), nullable=False)
    artist_wallet = Column(String(64), nullable=False, index=True)
    owner_wallet = Column(String(64), nullable=True, index=True)
    medium = Column(String(128), nullable=True)
    dimensions = Column(String(64), nullable=True)
    year = Column(Integer, nullable=True)
    genesis_vector_hash = Column(String(66), nullable=False)
    chip_id_hash = Column(String(66), nullable=False, index=True)
    metadata_uri = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="CLEAR", index=True) # CLEAR, CHIP_REPLACED, UNSYNCHRONIZED_OWNERSHIP, FLAGGED, DESTROYED
    onchain_tx_hash = Column(String(66), nullable=True)
    genesis_vector = Column(JSON, nullable=True)
    genesis_depth = Column(JSON, nullable=True)
    genesis_points = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class CaptureRecord(Base):
    """
    B-02 / D-05: 5-10 Point Guided Macro + LiDAR Surface Capture Record.
    """
    __tablename__ = "capture_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=True, index=True)
    point_index = Column(Integer, nullable=False, default=1)
    vector_hash = Column(String(66), nullable=False)
    relief_roughness = Column(Float, nullable=False, default=0.45)
    flat_print_passed = Column(Boolean, nullable=False, default=True)
    has_lidar = Column(Boolean, nullable=False, default=True)
    vector = Column(JSON, nullable=True)
    depth_stats = Column(JSON, nullable=True)
    intrinsics = Column(JSON, nullable=True)
    metadata_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class IntakeDossier(Base):
    """
    B-01 Intake Dossier -> B-07 Artist Co-Sign -> B-08 Gallery Safe Mint (SD-02).
    """
    __tablename__ = "intake_dossiers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False)
    artist_name = Column(String(255), nullable=False)
    artist_wallet = Column(String(64), nullable=False, index=True)
    gallery_wallet = Column(String(64), nullable=False, index=True)
    medium = Column(String(128), nullable=True)
    dimensions = Column(String(64), nullable=True)
    year = Column(Integer, nullable=True)
    condition_notes = Column(Text, nullable=True)
    capture_ids = Column(JSON, nullable=False) # List of 5-10 scan capture UUIDs
    genesis_vector_hash = Column(String(66), nullable=False)
    chip_uid = Column(String(64), nullable=False)
    chip_id_hash = Column(String(66), nullable=False, unique=True)
    metadata_uri = Column(String(255), nullable=True)
    artist_co_signature = Column(Text, nullable=True) # ADR-02 / B-07
    token_id = Column(Integer, nullable=True)
    mint_tx_hash = Column(String(66), nullable=True)
    status = Column(String(32), nullable=False, default="AWAITING_ARTIST_COSIGN", index=True) # AWAITING_ARTIST_COSIGN, READY_FOR_SAFE_MINT, MINTED, REJECTED
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class NfcChip(Base):
    __tablename__ = "nfc_chips"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    chip_uid = Column(String(64), nullable=False, unique=True, index=True)
    chip_id_hash = Column(String(66), nullable=False, unique=True, index=True)
    token_id = Column(Integer, nullable=True, index=True)
    key_ref = Column(String(128), nullable=True) # Opaque KMS / Vault key ARN
    last_counter = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class ChipReplacement(Base):
    """
    UC-F & SD-08: 3-of-3 Multi-Approval Chip Replacement Tracker.
    """
    __tablename__ = "chip_replacements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=False, index=True)
    old_chip_id_hash = Column(String(66), nullable=False)
    new_chip_id_hash = Column(String(66), nullable=False)
    optical_similarity_bps = Column(Integer, nullable=False) # Must be >= 8800 bps
    status = Column(String(32), nullable=False, default="PENDING_APPROVALS") # PENDING_APPROVALS, READY_FOR_EXECUTION, COMPLETED, REJECTED
    collector_wallet = Column(String(64), nullable=False)
    artist_wallet = Column(String(64), nullable=False)
    verifier_wallet = Column(String(64), nullable=False)
    collector_signature = Column(Text, nullable=True) # 1/3
    artist_signature = Column(Text, nullable=True)    # 2/3
    verifier_signature = Column(Text, nullable=True)  # 3/3
    tx_hash = Column(String(66), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    approvals = relationship("ChipApproval", back_populates="replacement", cascade="all, delete-orphan")


class ChipApproval(Base):
    """
    F-05 & SD-08: Individual party approval signature for 3-of-3 Chip Replacement.
    """
    __tablename__ = "chip_approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    replacement_id = Column(String(36), ForeignKey("chip_replacements.id", ondelete="CASCADE"), nullable=False, index=True)
    party = Column(String(32), nullable=False)  # collector, artist, verifier
    signer_wallet = Column(String(64), nullable=False)
    signature = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    replacement = relationship("ChipReplacement", back_populates="approvals")


# ==============================================================================
# Domain 3 — Marketplace & Escrow (ERD 3)
# ==============================================================================

class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=False, index=True)
    artwork_title = Column(String(255), nullable=False)
    artist_name = Column(String(255), nullable=False)
    artist_wallet = Column(String(64), nullable=False)
    seller_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    seller_wallet = Column(String(64), nullable=False, index=True)
    price_amount = Column(Float, nullable=False)
    asset = Column(String(16), nullable=False, default="USDC")
    royalty_bps = Column(Integer, nullable=False, default=500)
    platform_fee_bps = Column(Integer, nullable=False, default=150)
    chip_uid = Column(String(64), nullable=False, default="04A1B2C3D4E580")
    genesis_vector_hash = Column(String(66), nullable=False, default="0x9c8b7a6f5e4d3c2b1a0987654321fedcba0987654321fedcba09876543210001")
    image_url = Column(String(512), nullable=True)
    medium = Column(String(128), nullable=True, default="Oil and impasto glaze on Belgian linen")
    dimensions = Column(String(64), nullable=True, default="120 x 95 cm")
    year = Column(Integer, nullable=True, default=2024)
    curation_notes = Column(Text, nullable=True)
    listing_sig = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    escrows = relationship("EscrowTransaction", back_populates="listing", cascade="all, delete-orphan")

class EscrowTransaction(Base):
    __tablename__ = "escrow_transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    listing_id = Column(String(36), ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    token_id = Column(Integer, nullable=False, index=True)
    buyer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    buyer_wallet = Column(String(64), nullable=False, index=True)
    wallet_provider = Column(String(32), nullable=False, default="metamask")
    gas_mode = Column(String(32), nullable=False, default="self_pay_l2")
    amount = Column(Float, nullable=False)
    asset = Column(String(16), nullable=False, default="USDC")
    permit2_signature = Column(Text, nullable=True)
    deposit_tx_hash = Column(String(66), nullable=False)
    l1_nfc_verified = Column(Boolean, nullable=False, default=False)
    l2_lidar_verified = Column(Boolean, nullable=False, default=False)
    l2_similarity_score = Column(Float, nullable=True)
    delivery_attestation_hash = Column(String(66), nullable=True)
    release_tx_hash = Column(String(66), nullable=True)
    seller_payout_amount = Column(Float, nullable=False)
    artist_royalty_amount = Column(Float, nullable=False)
    platform_fee_amount = Column(Float, nullable=False)
    treasury_safe_address = Column(String(64), nullable=False, default="0xSafeTreasuryArthentic0000000000000008453")
    dispute_reason = Column(Text, nullable=True)
    dispute_evidence_uri = Column(String(255), nullable=True)
    resolution_note = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="LOCKED", index=True)
    timeout_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    listing = relationship("MarketplaceListing", back_populates="escrows")

# ==============================================================================
# Domain 4 — Verification, Attestation & Provenance (ERD 4)
# ==============================================================================

class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=False, index=True)
    level = Column(Integer, nullable=False) # 1 or 2
    similarity_bps = Column(Integer, nullable=False)
    sun_digest = Column(String(66), nullable=False)
    status = Column(String(32), nullable=False) # VALID, FAILED
    verifier_wallet = Column(String(64), nullable=True)
    attestation_signature = Column(Text, nullable=True)
    recorded_onchain = Column(Boolean, nullable=False, default=False)
    tx_hash = Column(String(66), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class ProvenanceEventModel(Base):
    __tablename__ = "provenance_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor = Column(String(64), nullable=False)
    role = Column(String(32), nullable=False)
    details = Column(Text, nullable=False)
    tx_hash = Column(String(66), nullable=True)
    merkle_batch_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ChainEvent(Base):
    """
    SD-12: Reorg-safe indexed L2 blockchain log event.
    """
    __tablename__ = "chain_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    chain_id = Column(Integer, nullable=False, default=84532, index=True)
    block_number = Column(Integer, nullable=False, index=True)
    block_hash = Column(String(66), nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False, index=True)
    log_index = Column(Integer, nullable=False, default=0)
    contract_address = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False, index=True)
    token_id = Column(Integer, nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    finalized = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MerkleBatch(Base):
    """
    H-05 & SD-10: Ethereum L1 Merkle Anchor batch.
    """
    __tablename__ = "merkle_batches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    root = Column(String(66), nullable=False, unique=True, index=True)
    from_block = Column(Integer, nullable=False)
    to_block = Column(Integer, nullable=False)
    event_count = Column(Integer, nullable=False)
    l1_tx_hash = Column(String(66), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING") # PENDING, ANCHORED, CONFIRMED
    anchored_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class IndexerCursor(Base):
    __tablename__ = "indexer_cursors"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    chain_id = Column(Integer, unique=True, nullable=False)
    last_block_number = Column(Integer, nullable=False, default=0)
    last_block_hash = Column(String(66), nullable=False, default="0x0")
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

# ==============================================================================
# Domain 5 — Restoration (ERD 5)
# ==============================================================================

class RestorationRequest(Base):
    """
    E-01 Restoration Request from Collector to Accredited Conservator.
    """
    __tablename__ = "restoration_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    token_id = Column(Integer, nullable=False, index=True)
    owner_wallet = Column(String(64), nullable=False, index=True)
    conservator_wallet = Column(String(64), nullable=False, index=True)
    damage_description = Column(Text, nullable=False)
    damage_photos = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="PENDING", index=True) # PENDING, IN_PROGRESS, AWAITING_OWNER_CONSENT, FINALIZED, REJECTED
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class RestorationReport(Base):
    """
    E-04 Treatment Report + E-07* Owner Consent + E-03 Finalize updateCondition.
    """
    __tablename__ = "restoration_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    request_id = Column(String(36), ForeignKey("restoration_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    token_id = Column(Integer, nullable=False, index=True)
    conservator_wallet = Column(String(64), nullable=False)
    new_vector_hash = Column(String(66), nullable=False)
    note_uri = Column(String(255), nullable=False)
    treatment_summary = Column(Text, nullable=False)
    condition_grade = Column(String(32), nullable=False, default="STABLE")
    owner_consent_sig = Column(Text, nullable=True) # ADR-03 / E-07*
    tx_hash = Column(String(66), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

# ==============================================================================
# Domain 6 — Governance, Paymaster & Incidents (ERD 6)
# ==============================================================================

class SecurityIncident(Base):
    """
    J-05 Incident Console & SD-11 Security Stream.
    """
    __tablename__ = "security_incidents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    incident_type = Column(String(64), nullable=False, index=True) # SUN_REPLAY, FAILED_CLAIMS_BURST, REORG_DETECTED, SIGNER_ANOMALY
    severity = Column(String(16), nullable=False, default="MEDIUM") # LOW, MEDIUM, HIGH, CRITICAL
    target_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=False)
    meta = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="OPEN", index=True) # OPEN, INVESTIGATING, RESOLVED, CIRCUIT_BREAKER_TRIGGERED
    action_taken = Column(String(64), nullable=True) # PAUSED, REVOKED, REWOUND, DISMISSED
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

class PaymasterPolicy(Base):
    """
    K-01 Sponsorship Tiers (T1, T2, T3) and K-02 Per-Wallet Quotas.
    """
    __tablename__ = "paymaster_policies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tier = Column(String(16), nullable=False, unique=True) # T1, T2, T3
    name = Column(String(128), nullable=False)
    allowed_selectors = Column(JSON, nullable=False) # List of 4-byte selectors
    monthly_quota = Column(Integer, nullable=False) # e.g. 10, 25, 5
    max_gas_wei = Column(String(32), nullable=False, default="35000000000000") # 350,000 gas
    is_active = Column(Boolean, nullable=False, default=True)

class SponsoredTx(Base):
    __tablename__ = "sponsored_txs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tx_hash = Column(String(66), nullable=False, unique=True, index=True)
    user_wallet = Column(String(64), nullable=False, index=True)
    tier = Column(String(16), nullable=False)
    function_name = Column(String(64), nullable=False)
    gas_used = Column(Integer, nullable=False)
    gas_cost_wei = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SignerKey(Base):
    """
    SC-NODE-01 & A-09/A-10: Protocol Node HSM/KMS Signer Key Registry.
    """
    __tablename__ = "signer_keys"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key_id = Column(String(128), nullable=False, unique=True, index=True)
    kms_arn = Column(String(255), nullable=False)
    kms_key_id = synonym("kms_arn")
    public_address = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="PROTOCOL_NODE_ROLE")
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)  # ACTIVE, ROTATED, REVOKED
    rotated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

