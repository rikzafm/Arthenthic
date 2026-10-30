"""
server/indexer/merkle_batcher.py
Layer 4: Ethereum L1 Merkle Root Batch Worker & Inclusion Proof Engine (H-05 / SD-10).
Batches finalized Base L2 provenance events, constructs sorted Merkle tree,
anchors root onto Ethereum Sepolia L1 MerkleAnchor contract via chain_client,
and generates/verifies proofs for mobile and web clients.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session as DBSession

from server.db.database import SessionLocal
from server.db.models import MerkleBatch, ProvenanceEventModel
from server.node.chain_client import chain_client


def _hash_leaf(event: ProvenanceEventModel) -> str:
    """Computes sorted leaf hash: sha256(tokenId:eventType:txHash:id)"""
    payload = (
        f"{event.token_id}:{event.event_type}:{event.tx_hash or ''}:{event.id}"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _hash_pair(left: str, right: str) -> str:
    if left > right:
        left, right = right, left
    return hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest()


class MerkleBatchWorker:
    def __init__(self, batch_size_threshold: int = 10):
        self.batch_size_threshold = batch_size_threshold

    def build_merkle_tree(
        self, leaves: List[str]
    ) -> Tuple[str, List[List[str]]]:
        """
        Builds a sorted binary Merkle tree. Returns (root_hex, tree_levels).
        """
        if not leaves:
            empty_root = "0x" + "0" * 64
            return empty_root, [[]]

        current_level = sorted([l[2:].lower() if l.startswith("0x") else l.lower() for l in leaves])
        tree = [current_level]

        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = (
                    current_level[i + 1]
                    if i + 1 < len(current_level)
                    else current_level[i]
                )
                next_level.append(_hash_pair(left, right))
            current_level = next_level
            tree.append(current_level)

        return "0x" + tree[-1][0], tree

    def get_inclusion_proof(
        self, tree: List[List[str]], leaf: str
    ) -> List[Dict[str, str]]:
        """Generates audit proof for leaf up to root."""
        proof: List[Dict[str, str]] = []
        if not tree or not tree[0]:
            return proof

        current = leaf[2:].lower() if leaf.startswith("0x") else leaf.lower()
        for level in tree[:-1]:
            if current not in level:
                break
            idx = level.index(current)
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(level) else idx
                position = "right"
            else:
                sibling_idx = idx - 1
                position = "left"

            sibling = level[sibling_idx]
            proof.append({"position": position, "sibling": "0x" + sibling})
            if position == "left":
                current = _hash_pair(sibling, current)
            else:
                current = _hash_pair(current, sibling)

        return proof

    def verify_inclusion_proof(
        self, root_hex: str, leaf: str, proof: List[Dict[str, str]]
    ) -> bool:
        """
        Verifies a Merkle inclusion proof against the anchored root_hex (H-05).
        """
        if not proof:
            return False
        current = leaf[2:].lower() if leaf.startswith("0x") else leaf.lower()
        for step in proof:
            sib_raw = step.get("sibling", "")
            sibling = sib_raw[2:].lower() if sib_raw.startswith("0x") else sib_raw.lower()
            if step.get("position") == "left":
                current = _hash_pair(sibling, current)
            else:
                current = _hash_pair(current, sibling)
        expected_root = root_hex if root_hex.startswith("0x") else "0x" + root_hex
        return ("0x" + current).lower() == expected_root.lower()

    def trigger_batch_anchor(
        self, db: Optional[DBSession] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Checks for unanchored provenance events. Generates Merkle root and broadcasts
        MerkleAnchor.anchorRoot(root, fromBlock, toBlock) to Ethereum Sepolia L1 via chain_client.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            unanchored = (
                db.query(ProvenanceEventModel)
                .filter(ProvenanceEventModel.merkle_batch_id.is_(None))
                .order_by(ProvenanceEventModel.created_at.asc())
                .all()
            )

            if len(unanchored) < 1:
                return None

            leaves = [_hash_leaf(ev) for ev in unanchored]
            root_hex, _ = self.build_merkle_tree(leaves)

            from_block = 1000000
            to_block = from_block + len(unanchored)
            l1_receipt = chain_client.anchor_merkle_root_l1(
                root_hex=root_hex, from_block=from_block, to_block=to_block
            )
            l1_tx_hash = l1_receipt["l1_tx_hash"]

            batch = MerkleBatch(
                root=root_hex,
                from_block=from_block,
                to_block=to_block,
                event_count=len(unanchored),
                l1_tx_hash=l1_tx_hash,
                status="ANCHORED",
                anchored_at=datetime.now(timezone.utc),
            )
            db.add(batch)
            db.commit()
            db.refresh(batch)

            for ev in unanchored:
                ev.merkle_batch_id = batch.id
            db.commit()

            return {
                "batch_id": batch.id,
                "root": root_hex,
                "event_count": len(unanchored),
                "l1_tx_hash": l1_tx_hash,
                "l1_chain_id": l1_receipt["chain_id"],
                "merkle_anchor_address": l1_receipt["contract_address"],
                "status": "ANCHORED",
            }
        finally:
            if should_close:
                db.close()


merkle_worker = MerkleBatchWorker()
MerkleBatcher = MerkleBatchWorker

def verify_inclusion_proof(root_hex: str, leaf: str, proof: List[Dict[str, str]]) -> bool:
    return merkle_worker.verify_inclusion_proof(root_hex, leaf, proof)

