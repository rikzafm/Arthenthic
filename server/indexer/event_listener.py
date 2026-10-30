"""
server/indexer/event_listener.py
Layer 4: Reorg-Safe Chain Event Indexer (SD-12 & Part II, Section 3.4).
Subscribes to Base Sepolia L2 logs (ArthenticNFT & ArthenticEscrow).
Tracks block continuity, detects L2 reorgs, unwinds unfinalized ChainEvent rows,
and marks events finalized once depth >= 12 blocks.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session as DBSession

from server.db.database import SessionLocal
from server.db.models import (
    ChainEvent,
    IndexerCursor,
    ProvenanceEventModel,
    SecurityIncident,
)
from server.db.redis_hotpath import redis_hotpath
from server.node.chain_client import chain_client

CONFIRMATION_DEPTH = 12


class ReorgSafeEventListener:
    def __init__(self, chain_id: int = 84532):
        self.chain_id = chain_id

    def process_incoming_block(
        self,
        block_number: int,
        block_hash: str,
        parent_hash: str,
        logs: List[Dict[str, Any]],
        db: Optional[DBSession] = None,
    ) -> Dict[str, Any]:
        """
        Processes a new block with reorg detection, unfinalized ChainEvent rollback,
        and 12-block finality promotion.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            cursor = (
                db.query(IndexerCursor)
                .filter(IndexerCursor.chain_id == self.chain_id)
                .first()
            )
            if not cursor:
                cursor = IndexerCursor(
                    chain_id=self.chain_id,
                    last_block_number=block_number - 1,
                    last_block_hash=parent_hash,
                )
                db.add(cursor)
                db.commit()

            reorg_detected = False
            # Check block continuity: incoming parent_hash must match last_block_hash
            if (
                cursor.last_block_number > 0
                and block_number == cursor.last_block_number + 1
            ):
                if (
                    parent_hash != cursor.last_block_hash
                    and cursor.last_block_hash != "0x0"
                ):
                    reorg_detected = True

            if reorg_detected:
                # 1. Log incident (J-05)
                incident = SecurityIncident(
                    incident_type="REORG_DETECTED",
                    severity="HIGH",
                    details=(
                        f"Chain reorg detected on chain {self.chain_id} at block {block_number}. "
                        f"Rewinding from {cursor.last_block_hash} to {parent_hash}."
                    ),
                    meta={
                        "fork_block": block_number,
                        "old_head": cursor.last_block_hash,
                        "new_parent": parent_hash,
                    },
                    status="RESOLVED",
                    action_taken="REWOUND",
                )
                db.add(incident)

                # 2. Roll back unfinalized ChainEvent rows from the orphaned tip
                (
                    db.query(ChainEvent)
                    .filter(
                        ChainEvent.chain_id == self.chain_id,
                        ChainEvent.finalized.is_(False),
                        ChainEvent.block_number >= cursor.last_block_number,
                    )
                    .delete(synchronize_session=False)
                )

                cursor.last_block_number = block_number - 1
                cursor.last_block_hash = parent_hash

            # Process logs in this block
            processed_count = 0
            for idx, log in enumerate(logs):
                event_type = log.get("event_type", "UNKNOWN")
                token_id = int(log.get("token_id", 101))
                actor = log.get("actor", "0x0")
                role = log.get("role", "Protocol")
                details = log.get("details", "")
                tx_hash = log.get(
                    "tx_hash",
                    "0x"
                    + hashlib.sha256(f"{block_number}:{idx}:{log}".encode()).hexdigest(),
                )

                chain_ev = ChainEvent(
                    chain_id=self.chain_id,
                    block_number=block_number,
                    block_hash=block_hash,
                    tx_hash=tx_hash,
                    log_index=idx,
                    contract_address=log.get(
                        "contract_address", chain_client.nft_address
                    ),
                    event_type=event_type,
                    token_id=token_id,
                    payload=log,
                    finalized=False,
                )
                db.add(chain_ev)

                # Add to provenance_events
                ev = ProvenanceEventModel(
                    token_id=token_id,
                    event_type=event_type,
                    actor=actor,
                    role=role,
                    details=details,
                    tx_hash=tx_hash,
                )
                db.add(ev)
                processed_count += 1

            # Mark events at or below (block_number - CONFIRMATION_DEPTH) as finalized
            finality_cutoff = block_number - CONFIRMATION_DEPTH
            if finality_cutoff > 0:
                (
                    db.query(ChainEvent)
                    .filter(
                        ChainEvent.chain_id == self.chain_id,
                        ChainEvent.finalized.is_(False),
                        ChainEvent.block_number <= finality_cutoff,
                    )
                    .update({"finalized": True}, synchronize_session=False)
                )

            # Advance cursor
            cursor.last_block_number = block_number
            cursor.last_block_hash = block_hash
            cursor.updated_at = datetime.now(timezone.utc)

            # Update Redis Hot-Path Key #6: idx:head:{chainId}
            redis_hotpath.update_indexer_head(
                self.chain_id, block_number, block_hash
            )

            db.commit()

            return {
                "success": True,
                "chain_id": self.chain_id,
                "block_number": block_number,
                "block_hash": block_hash,
                "reorg_handled": reorg_detected,
                "events_indexed": processed_count,
            }
        finally:
            if should_close:
                db.close()


indexer_listener = ReorgSafeEventListener()
