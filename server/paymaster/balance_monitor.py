"""
server/paymaster/balance_monitor.py
Layer 5: EntryPoint Deposit Monitor & Cost Ledger (K-03 / K-05).
Tracks Paymaster EntryPoint deposit on Base L2, logs gas burn into sponsored_txs,
and emits alerts when balance falls below emergency threshold.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session as DBSession
from server.db.database import SessionLocal
from server.db.models import SponsoredTx, SecurityIncident
from server.db.redis_hotpath import redis_hotpath

LOW_BALANCE_THRESHOLD_WEI = 100000000000000000  # 0.1 ETH

class PaymasterBalanceMonitor:
    def __init__(self, chain_id: int = 84532):
        self.chain_id = chain_id

    def update_balance(self, balance_wei: int, db: Optional[DBSession] = None) -> Dict[str, Any]:
        """
        Updates cached balance and checks against threshold.
        """
        status = "ok"
        if balance_wei <= 0:
            status = "empty"
        elif balance_wei < LOW_BALANCE_THRESHOLD_WEI:
            status = "warning"

        # Update Redis hotpath cache (Key #5)
        redis_hotpath.set_paymaster_balance(self.chain_id, balance_wei, status)

        # Log security incident if warning or empty
        if status in ("warning", "empty"):
            should_close = False
            if db is None:
                db = SessionLocal()
                should_close = True
            try:
                incident = SecurityIncident(
                    incident_type="PAYMASTER_LOW_BALANCE",
                    severity="HIGH" if status == "empty" else "MEDIUM",
                    details=f"Paymaster balance for chain {self.chain_id} is low: {balance_wei / 1e18:.4f} ETH (Status: {status})",
                    status="OPEN",
                )
                db.add(incident)
                db.commit()
            finally:
                if should_close:
                    db.close()

        return {
            "chain_id": self.chain_id,
            "balance_wei": str(balance_wei),
            "balance_eth": balance_wei / 1e18,
            "status": status,
        }

    def check_balance_health(self) -> Dict[str, Any]:
        """
        Returns cached Paymaster balance health status from Redis hot-path.
        """
        bal = redis_hotpath.get_paymaster_balance(self.chain_id)
        return {
            "chain_id": self.chain_id,
            "status": bal.get("status", "ok"),
            "balance_wei": bal.get("balance_wei", "1000000000000000000"),
        }

    def record_sponsored_tx(
        self,
        tx_hash: str,
        user_wallet: str,
        tier: str,
        function_name: str,
        gas_used: int,
        gas_cost_wei: str,
        db: Optional[DBSession] = None,
    ) -> Dict[str, Any]:
        """
        K-05: Records gas sponsorship into cost ledger for accounting.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            tx = SponsoredTx(
                tx_hash=tx_hash,
                user_wallet=user_wallet.lower(),
                tier=tier,
                function_name=function_name,
                gas_used=gas_used,
                gas_cost_wei=gas_cost_wei,
            )
            db.add(tx)
            db.commit()
            return {"recorded": True, "tx_hash": tx_hash}
        finally:
            if should_close:
                db.close()

balance_monitor = PaymasterBalanceMonitor()
paymaster_balance_monitor = balance_monitor


