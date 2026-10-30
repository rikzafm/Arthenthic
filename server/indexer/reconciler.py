"""
server/indexer/reconciler.py
Layer 4: Chain-vs-Database Drift Reconciler (Part II, Section 3.4).
Periodic reconciler comparing on-chain state (ArthenticNFT.ownerOf, ArthenticNFT.genesisHash)
against off-chain database records and healing discrepancies.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session as DBSession
from server.db.database import SessionLocal
from server.db.models import Artwork, MarketplaceListing

class ChainDriftReconciler:
    def __init__(self, chain_id: int = 84532):
        self.chain_id = chain_id

    def reconcile_token_ownership(
        self,
        token_id: int,
        onchain_owner: str,
        db: Optional[DBSession] = None
    ) -> Dict[str, Any]:
        """
        Heals ownership drift: If on-chain owner != db owner, updates db.
        If on-chain owner != active listing seller, marks listing UNSYNCHRONIZED_OWNERSHIP (C-12).
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            norm_onchain = onchain_owner.lower()
            artwork = db.query(Artwork).filter(Artwork.token_id == token_id).first()
            drift_detected = False

            if artwork:
                if artwork.owner_wallet and artwork.owner_wallet.lower() != norm_onchain:
                    drift_detected = True
                    artwork.owner_wallet = norm_onchain

            # Check marketplace listing synchronization (C-12)
            listing = db.query(MarketplaceListing).filter(
                MarketplaceListing.token_id == token_id,
                MarketplaceListing.status == "ACTIVE"
            ).first()

            if listing:
                if listing.seller_wallet.lower() != norm_onchain:
                    # Physical seller does not match on-chain owner!
                    if artwork:
                        artwork.status = "UNSYNCHRONIZED_OWNERSHIP"
                    return {
                        "token_id": token_id,
                        "synchronized": False,
                        "status": "UNSYNCHRONIZED_OWNERSHIP",
                        "seller_wallet": listing.seller_wallet,
                        "onchain_owner": norm_onchain,
                        "action": "Listing flagged: physical seller does not hold on-chain NFT."
                    }

            db.commit()
            return {
                "token_id": token_id,
                "synchronized": True,
                "status": artwork.status if artwork else "CLEAR",
                "drift_healed": drift_detected,
                "current_owner": norm_onchain,
            }
        finally:
            if should_close:
                db.close()

drift_reconciler = ChainDriftReconciler()

