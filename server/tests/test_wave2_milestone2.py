"""
server/tests/test_wave2_milestone2.py
Test-First Suite for Wave 2 Milestone 2 (Live Testnet RPC Broadcast, Consolidated 6-Domain
Alembic Migration, ChainEvent Reorg Rollback, Merkle Inclusion Proof Verification,
Genesis Dossiers API, and C-12 Expired Escrow Sweep).
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.db.database import SessionLocal
from server.db.models import (
    Artwork,
    CaptureRecord,
    ChainEvent,
    ChipApproval,
    ChipReplacement,
    EscrowTransaction,
    IntakeDossier,
    MarketplaceListing,
    SignerKey,
)
from server.indexer.event_listener import indexer_listener
from server.indexer.merkle_batcher import merkle_worker
from server.node.chain_client import EVMChainClient, chain_client

client = TestClient(app)


def test_chain_client_manifest_and_rpc_methods():
    """
    Verifies EVMChainClient provides Base Sepolia (84532) & Ethereum Sepolia (11155111)
    deployment manifest, read helpers (ownerOf, genesisHash, is_chip_bound, get_listing_state),
    and transaction broadcast helpers (genesisMint, updateCondition, replaceChip, refund, anchorRoot).
    """
    manifest = chain_client.get_contract_deployment_manifest()
    assert manifest["base_sepolia"]["chain_id"] == 84532
    assert "ArthenticNFT" in manifest["base_sepolia"]["contracts"]
    assert "ArthenticEscrow" in manifest["base_sepolia"]["contracts"]
    assert manifest["ethereum_sepolia"]["chain_id"] == 11155111
    assert "MerkleAnchor" in manifest["ethereum_sepolia"]["contracts"]

    # Read helpers with fallback when offline
    assert (
        chain_client.get_onchain_owner(101, fallback_owner="0xabc") == "0xabc"
    )
    assert (
        chain_client.get_genesis_hash(101, fallback_hash="0xgen101") == "0xgen101"
    )
    assert chain_client.is_chip_bound("0xchip101", fallback_bound=True) is True
    listing_state = chain_client.get_listing_state(
        1, fallback_state={"status": "ACTIVE", "price": 12500}
    )
    assert listing_state["status"] == "ACTIVE"

    # Broadcast helpers
    mint_receipt = chain_client.broadcast_genesis_mint(
        artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
        genesis_vector_hash="0x" + "11" * 32,
        chip_id_hash="0x" + "22" * 32,
        metadata_uri="ar://dossier_1",
        artist_co_signature="0x" + "33" * 65,
    )
    assert mint_receipt["chain_id"] == 84532
    assert mint_receipt["method"] == "genesisMint"
    assert mint_receipt["tx_hash"].startswith("0x")

    cond_receipt = chain_client.broadcast_update_condition(
        token_id=101,
        new_vector_hash="0x" + "44" * 32,
        note_uri="ar://restoration_note",
        owner_consent_sig="0x" + "55" * 65,
    )
    assert cond_receipt["chain_id"] == 84532
    assert cond_receipt["method"] == "updateCondition"
    assert cond_receipt["tx_hash"].startswith("0x")

    chip_receipt = chain_client.broadcast_replace_chip(
        token_id=101,
        new_chip_id_hash="0x" + "66" * 32,
        optical_similarity_bps=9420,
        approvals=["0xsig1", "0xsig2", "0xsig3"],
    )
    assert chip_receipt["chain_id"] == 84532
    assert chip_receipt["method"] == "replaceChip"
    assert chip_receipt["tx_hash"].startswith("0x")

    refund_receipt = chain_client.broadcast_escrow_refund(listing_id="listing-1")
    assert refund_receipt["chain_id"] == 84532
    assert refund_receipt["method"] == "refund"
    assert refund_receipt["tx_hash"].startswith("0x")


def test_contracts_config_endpoint():
    """Verifies GET /v1/contracts/config returns live contract deployment manifest for clients."""
    res = client.get("/v1/contracts/config")
    assert res.status_code == 200
    data = res.json()
    assert data["base_sepolia"]["chain_id"] == 84532
    assert data["ethereum_sepolia"]["chain_id"] == 11155111
    assert "selectors" in data


def test_complete_6_domain_models_and_consolidated_alembic_migration():
    """
    Verifies all Domain 2-6 models (including CaptureRecord, ChainEvent, ChipApproval, SignerKey)
    exist and the consolidated Alembic migration file defines all tables + PostgreSQL triggers
    for forbid_genesis_change() (SC-GEN-01) and append-only audit_log.
    """
    assert CaptureRecord.__tablename__ == "capture_records"
    assert ChainEvent.__tablename__ == "chain_events"
    assert ChipApproval.__tablename__ == "chip_approvals"
    assert SignerKey.__tablename__ == "signer_keys"

    versions_dir = (
        Path(__file__).resolve().parent.parent / "alembic" / "versions"
    )
    migration_files = list(versions_dir.glob("*.py"))
    combined_source = "\n".join(
        f.read_text(encoding="utf-8") for f in migration_files
    )

    required_tables = [
        "artworks",
        "capture_records",
        "intake_dossiers",
        "nfc_chips",
        "chip_replacements",
        "chip_approvals",
        "marketplace_listings",
        "escrow_transactions",
        "verification_records",
        "provenance_events",
        "chain_events",
        "merkle_batches",
        "indexer_cursors",
        "restoration_requests",
        "restoration_reports",
        "security_incidents",
        "paymaster_policies",
        "sponsored_txs",
        "signer_keys",
    ]
    for tbl in required_tables:
        assert tbl in combined_source, f"Missing table {tbl} in Alembic migrations"

    # Invariant SC-GEN-01 trigger & append-only audit_log trigger
    assert "forbid_genesis_change" in combined_source
    assert "forbid_audit_log_mutation" in combined_source


def test_indexer_chain_events_reorg_rollback_and_merkle_proof_verification():
    """
    Verifies ChainEvent persistence, reorg rollback of unfinalized ChainEvent rows (SD-12),
    confirmation finality after 12 blocks, and MerkleBatchWorker.verify_inclusion_proof (H-05).
    """
    db = SessionLocal()
    try:
        # Process block 2000
        res1 = indexer_listener.process_incoming_block(
            block_number=2000,
            block_hash="0xhash2000",
            parent_hash="0xhash1999",
            logs=[
                {
                    "event_type": "GENESIS_MINTED",
                    "token_id": 202,
                    "actor": "0xartist202",
                    "role": "Artist",
                    "details": "Block 2000 mint",
                    "tx_hash": "0xtx_block_2000_a",
                }
            ],
            db=db,
        )
        assert res1["success"] is True

        # Process block 2001 on fork A
        res2 = indexer_listener.process_incoming_block(
            block_number=2001,
            block_hash="0xhash2001_forkA",
            parent_hash="0xhash2000",
            logs=[
                {
                    "event_type": "ESCROW_DEPOSITED",
                    "token_id": 202,
                    "actor": "0xbuyer202",
                    "role": "Collector",
                    "details": "Fork A deposit",
                    "tx_hash": "0xtx_block_2001_forkA",
                }
            ],
            db=db,
        )
        assert res2["reorg_handled"] is False

        # Simulate L2 reorg at block 2002 with a different parent_hash (Fork B replaces 2001)
        res_reorg = indexer_listener.process_incoming_block(
            block_number=2002,
            block_hash="0xhash2002_forkB",
            parent_hash="0xhash2001_forkB_DIFFERENT",
            logs=[
                {
                    "event_type": "ESCROW_CLAIMED",
                    "token_id": 202,
                    "actor": "0xbuyer202",
                    "role": "Collector",
                    "details": "Canonical Fork B claim",
                    "tx_hash": "0xtx_block_2002_forkB",
                }
            ],
            db=db,
        )
        assert res_reorg["reorg_handled"] is True

        # Advance 15 blocks ahead so block 2002 reaches confirmation depth (12)
        indexer_listener.process_incoming_block(
            block_number=2015,
            block_hash="0xhash2015",
            parent_hash="0xhash2014",
            logs=[],
            db=db,
        )
        ev_2002 = (
            db.query(ChainEvent)
            .filter(ChainEvent.tx_hash == "0xtx_block_2002_forkB")
            .first()
        )
        assert ev_2002 is not None
        assert ev_2002.finalized is True
    finally:
        db.close()

    # Verify Merkle proof generation & verification (H-05)
    leaves = ["leaf_a", "leaf_b", "leaf_c", "leaf_d"]
    root_hex, tree = merkle_worker.build_merkle_tree(leaves)
    proof = merkle_worker.get_inclusion_proof(tree, "leaf_b")
    assert merkle_worker.verify_inclusion_proof(root_hex, "leaf_b", proof) is True
    assert (
        merkle_worker.verify_inclusion_proof(root_hex, "tampered_leaf", proof)
        is False
    )


def test_genesis_dossiers_3_stage_workflow():
    """
    Verifies /v1/genesis/dossiers Stage 1 (Intake), Stage 2 (Co-Sign), and Stage 3 (Safe Mint)
    matching GenesisIntakeScreen and GallerySafeConsole.
    """
    unique_uid = "04D0551E" + datetime.now(timezone.utc).strftime("%H%M%S")
    # Stage 1: Create dossier
    r1 = client.post(
        "/v1/genesis/dossiers",
        json={
            "title": "Sunset Over Java Sea",
            "artist_name": "Raden Saleh Studio",
            "artist_wallet": "0x71C95911E9a5D330f4D621842EC243EE1343292e",
            "medium": "Oil on Linen",
            "dimensions": "140 x 100 cm",
            "year_created": 2026,
            "chip_uid": unique_uid,
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    dossier_id = d1["dossier_id"]
    assert d1["status"] == "AWAITING_ARTIST_COSIGN"

    # List dossiers
    r_list = client.get("/v1/genesis/dossiers")
    assert r_list.status_code == 200
    assert any(d["id"] == dossier_id for d in r_list.json()["dossiers"])

    # Stage 2: Artist EIP-712 Co-Sign
    r2 = client.post(
        f"/v1/genesis/dossiers/{dossier_id}/co-sign",
        json={
            "artist_wallet": "0x71C95911E9a5D330f4D621842EC243EE1343292e",
            "artist_eip712_sig": "0x" + "ab" * 65,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "READY_FOR_SAFE_MINT"

    # Stage 3: Gallery Safe Mint
    r3 = client.post(
        f"/v1/genesis/dossiers/{dossier_id}/mint",
        json={"safe_tx_hash": "0x" + "cd" * 32},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["feature_code"] == "B-08"
    assert d3["tx_hash"].startswith("0x")
    assert d3["token_id"] >= 101


def test_expired_escrow_auto_refund_with_real_locked_escrow():
    """
    Verifies C-12 sweep_expired_escrows accurately refunds a LOCKED EscrowTransaction
    whose timeout_at has expired, broadcasts refund via chain_client, and restores the listing to ACTIVE.
    """
    db = SessionLocal()
    try:
        listing = MarketplaceListing(
            token_id=999,
            artwork_title="Expired Transit Test Piece",
            artist_name="Test Artist",
            artist_wallet="0xArtist999",
            seller_wallet="0xSeller999",
            price_amount=5000.0,
            asset="USDC",
            status="ESCROW_LOCKED",
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)

        expired_escrow = EscrowTransaction(
            listing_id=listing.id,
            token_id=999,
            buyer_wallet="0xBuyer999",
            amount=5000.0,
            asset="USDC",
            deposit_tx_hash="0xdeposit999",
            seller_payout_amount=4675.0,
            artist_royalty_amount=250.0,
            platform_fee_amount=75.0,
            status="LOCKED",
            timeout_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(expired_escrow)
        db.commit()
        db.refresh(expired_escrow)
        escrow_id = expired_escrow.id
        listing_id = listing.id
    finally:
        db.close()

    sweep_res = client.post("/v1/marketplace/escrow/sweep-expired")
    assert sweep_res.status_code == 200
    sweep_data = sweep_res.json()
    assert escrow_id in sweep_data["refunded_escrow_ids"]

    db = SessionLocal()
    try:
        updated_esc = (
            db.query(EscrowTransaction)
            .filter(EscrowTransaction.id == escrow_id)
            .first()
        )
        updated_listing = (
            db.query(MarketplaceListing)
            .filter(MarketplaceListing.id == listing_id)
            .first()
        )
        assert updated_esc.status in ("REFUNDED", "REFUNDED_TO_BUYER")
        assert updated_esc.release_tx_hash is not None
        assert updated_listing.status == "ACTIVE"
    finally:
        db.close()

