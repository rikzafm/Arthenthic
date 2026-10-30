"""Consolidated Domain 2-6 Tables & Cryptographic Database Triggers (SC-GEN-01 & Append-Only Audit Log)

Revision ID: b8f291c04d12
Revises: a344005b4a98
Create Date: 2026-10-29 21:30:00.000000

Covers:
- Domain 2 (Artwork, Genesis & Chips): artworks, capture_records, intake_dossiers, nfc_chips, chip_replacements, chip_approvals
- Domain 3 (Marketplace & Escrow): marketplace_listings, escrow_transactions
- Domain 4 (Verification, Attestation & Provenance): verification_records, provenance_events, chain_events, merkle_batches, indexer_cursors
- Domain 5 (Restoration): restoration_requests, restoration_reports
- Domain 6 (Governance, Paymaster & Incidents): security_incidents, paymaster_policies, sponsored_txs, signer_keys
- PostgreSQL Triggers: forbid_genesis_change() (SC-GEN-01) and forbid_audit_log_mutation()
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "b8f291c04d12"
down_revision: Union[str, Sequence[str], None] = "a344005b4a98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Domain 2: Artwork, Genesis & Chips
    # ------------------------------------------------------------------
    op.create_table(
        "artworks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), unique=True, nullable=True, index=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist_name", sa.String(length=255), nullable=False),
        sa.Column("artist_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("owner_wallet", sa.String(length=64), nullable=True, index=True),
        sa.Column("medium", sa.String(length=128), nullable=True),
        sa.Column("dimensions", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("genesis_vector_hash", sa.String(length=66), nullable=False),
        sa.Column("chip_id_hash", sa.String(length=66), nullable=False, index=True),
        sa.Column("metadata_uri", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CLEAR", index=True),
        sa.Column("onchain_tx_hash", sa.String(length=66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "capture_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=True, index=True),
        sa.Column("point_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("vector_hash", sa.String(length=66), nullable=False),
        sa.Column("relief_roughness", sa.Float(), nullable=False, server_default="0.45"),
        sa.Column("flat_print_passed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("has_lidar", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "intake_dossiers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist_name", sa.String(length=255), nullable=False),
        sa.Column("artist_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("gallery_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("medium", sa.String(length=128), nullable=True),
        sa.Column("dimensions", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("condition_notes", sa.Text(), nullable=True),
        sa.Column("capture_ids", sa.JSON(), nullable=False),
        sa.Column("genesis_vector_hash", sa.String(length=66), nullable=False),
        sa.Column("chip_uid", sa.String(length=64), nullable=False),
        sa.Column("chip_id_hash", sa.String(length=66), nullable=False, unique=True),
        sa.Column("metadata_uri", sa.String(length=255), nullable=True),
        sa.Column("artist_co_signature", sa.Text(), nullable=True),
        sa.Column("token_id", sa.Integer(), nullable=True),
        sa.Column("mint_tx_hash", sa.String(length=66), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AWAITING_ARTIST_COSIGN", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "nfc_chips",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("chip_uid", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("chip_id_hash", sa.String(length=66), nullable=False, unique=True, index=True),
        sa.Column("token_id", sa.Integer(), nullable=True, index=True),
        sa.Column("key_ref", sa.String(length=128), nullable=True),
        sa.Column("last_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chip_replacements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("old_chip_id_hash", sa.String(length=66), nullable=False),
        sa.Column("new_chip_id_hash", sa.String(length=66), nullable=False),
        sa.Column("optical_similarity_bps", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING_APPROVALS"),
        sa.Column("collector_wallet", sa.String(length=64), nullable=False),
        sa.Column("artist_wallet", sa.String(length=64), nullable=False),
        sa.Column("verifier_wallet", sa.String(length=64), nullable=False),
        sa.Column("collector_signature", sa.Text(), nullable=True),
        sa.Column("artist_signature", sa.Text(), nullable=True),
        sa.Column("verifier_signature", sa.Text(), nullable=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chip_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("replacement_id", sa.String(length=36), sa.ForeignKey("chip_replacements.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("party", sa.String(length=32), nullable=False),
        sa.Column("signer_wallet", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # Domain 3: Marketplace & Escrow
    # ------------------------------------------------------------------
    op.create_table(
        "marketplace_listings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("artwork_title", sa.String(length=255), nullable=False),
        sa.Column("artist_name", sa.String(length=255), nullable=False),
        sa.Column("artist_wallet", sa.String(length=64), nullable=False),
        sa.Column("seller_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("seller_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("price_amount", sa.Float(), nullable=False),
        sa.Column("asset", sa.String(length=16), nullable=False, server_default="USDC"),
        sa.Column("royalty_bps", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("platform_fee_bps", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("chip_uid", sa.String(length=64), nullable=False),
        sa.Column("genesis_vector_hash", sa.String(length=66), nullable=False),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("medium", sa.String(length=128), nullable=True),
        sa.Column("dimensions", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("curation_notes", sa.Text(), nullable=True),
        sa.Column("listing_sig", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "escrow_transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("listing_id", sa.String(length=36), sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("buyer_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("buyer_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("wallet_provider", sa.String(length=32), nullable=False, server_default="metamask"),
        sa.Column("gas_mode", sa.String(length=32), nullable=False, server_default="self_pay_l2"),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("asset", sa.String(length=16), nullable=False, server_default="USDC"),
        sa.Column("permit2_signature", sa.Text(), nullable=True),
        sa.Column("deposit_tx_hash", sa.String(length=66), nullable=False),
        sa.Column("l1_nfc_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("l2_lidar_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("l2_similarity_score", sa.Float(), nullable=True),
        sa.Column("delivery_attestation_hash", sa.String(length=66), nullable=True),
        sa.Column("release_tx_hash", sa.String(length=66), nullable=True),
        sa.Column("seller_payout_amount", sa.Float(), nullable=False),
        sa.Column("artist_royalty_amount", sa.Float(), nullable=False),
        sa.Column("platform_fee_amount", sa.Float(), nullable=False),
        sa.Column("treasury_safe_address", sa.String(length=64), nullable=False),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.Column("dispute_evidence_uri", sa.String(length=255), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="LOCKED", index=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # Domain 4: Verification, Attestation & Provenance
    # ------------------------------------------------------------------
    op.create_table(
        "verification_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("similarity_bps", sa.Integer(), nullable=False),
        sa.Column("sun_digest", sa.String(length=66), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verifier_wallet", sa.String(length=64), nullable=True),
        sa.Column("attestation_signature", sa.Text(), nullable=True),
        sa.Column("recorded_onchain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "provenance_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("merkle_batch_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chain_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="84532", index=True),
        sa.Column("block_number", sa.Integer(), nullable=False, index=True),
        sa.Column("block_hash", sa.String(length=66), nullable=False, index=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=False, index=True),
        sa.Column("log_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contract_address", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("token_id", sa.Integer(), nullable=True, index=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("finalized", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "merkle_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("root", sa.String(length=66), nullable=False, unique=True, index=True),
        sa.Column("from_block", sa.Integer(), nullable=False),
        sa.Column("to_block", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("l1_tx_hash", sa.String(length=66), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "indexer_cursors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("chain_id", sa.Integer(), unique=True, nullable=False),
        sa.Column("last_block_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_block_hash", sa.String(length=66), nullable=False, server_default="0x0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # Domain 5: Restoration
    # ------------------------------------------------------------------
    op.create_table(
        "restoration_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("owner_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("conservator_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("damage_description", sa.Text(), nullable=False),
        sa.Column("damage_photos", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "restoration_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), sa.ForeignKey("restoration_requests.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_id", sa.Integer(), nullable=False, index=True),
        sa.Column("conservator_wallet", sa.String(length=64), nullable=False),
        sa.Column("new_vector_hash", sa.String(length=66), nullable=False),
        sa.Column("note_uri", sa.String(length=255), nullable=False),
        sa.Column("treatment_summary", sa.Text(), nullable=False),
        sa.Column("condition_grade", sa.String(length=32), nullable=False, server_default="STABLE"),
        sa.Column("owner_consent_sig", sa.Text(), nullable=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # Domain 6: Governance, Paymaster & Incidents
    # ------------------------------------------------------------------
    op.create_table(
        "security_incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN", index=True),
        sa.Column("action_taken", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "paymaster_policies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tier", sa.String(length=16), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("allowed_selectors", sa.JSON(), nullable=False),
        sa.Column("monthly_quota", sa.Integer(), nullable=False),
        sa.Column("max_gas_wei", sa.String(length=32), nullable=False, server_default="35000000000000"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "sponsored_txs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=False, unique=True, index=True),
        sa.Column("user_wallet", sa.String(length=64), nullable=False, index=True),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("function_name", sa.String(length=64), nullable=False),
        sa.Column("gas_used", sa.Integer(), nullable=False),
        sa.Column("gas_cost_wei", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "signer_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key_id", sa.String(length=128), nullable=False, unique=True, index=True),
        sa.Column("kms_arn", sa.String(length=255), nullable=False),
        sa.Column("public_address", sa.String(length=64), nullable=False, index=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="PROTOCOL_NODE_ROLE"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------
    # PostgreSQL Triggers: SC-GEN-01 (forbid_genesis_change) & Append-Only Audit Log
    # ------------------------------------------------------------------
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION forbid_genesis_change()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.genesis_vector_hash IS DISTINCT FROM NEW.genesis_vector_hash THEN
                    RAISE EXCEPTION 'Invariant SC-GEN-01 Violation: genesis_vector_hash is immutable once minted.';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_forbid_genesis_change
            BEFORE UPDATE ON artworks
            FOR EACH ROW
            EXECUTE FUNCTION forbid_genesis_change();
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION forbid_audit_log_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'AuditLog Invariant Violation: audit_log is strictly append-only.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_forbid_audit_log_mutation
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW
            EXECUTE FUNCTION forbid_audit_log_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_forbid_audit_log_mutation ON audit_log;")
        op.execute("DROP FUNCTION IF EXISTS forbid_audit_log_mutation();")
        op.execute("DROP TRIGGER IF EXISTS trg_forbid_genesis_change ON artworks;")
        op.execute("DROP FUNCTION IF EXISTS forbid_genesis_change();")

    op.drop_table("signer_keys")
    op.drop_table("sponsored_txs")
    op.drop_table("paymaster_policies")
    op.drop_table("security_incidents")
    op.drop_table("restoration_reports")
    op.drop_table("restoration_requests")
    op.drop_table("indexer_cursors")
    op.drop_table("merkle_batches")
    op.drop_table("chain_events")
    op.drop_table("provenance_events")
    op.drop_table("verification_records")
    op.drop_table("escrow_transactions")
    op.drop_table("marketplace_listings")
    op.drop_table("chip_approvals")
    op.drop_table("chip_replacements")
    op.drop_table("nfc_chips")
    op.drop_table("intake_dossiers")
    op.drop_table("capture_records")
    op.drop_table("artworks")

