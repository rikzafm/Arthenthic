"""
server/paymaster/policy_engine.py
Layer 5: ERC-4337 Paymaster & Meta-Transaction Policy Engine (SD-09 & Part II, Section 3.5).
Evaluates sponsorship eligibility across Tiers T1, T2, and T3 (K-01).
Enforces atomic Redis per-wallet monthly quotas (K-02).
Triggers K-04 Self-Pay fallback modal when quota is exceeded or balance is low.
Supports live ERC-4337 Bundler / Paymaster RPC (Pimlico / Alchemy / Coinbase Paymaster)
pm_sponsorUserOperation with KMS-isolated paymasterAndData fallback signing.
"""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from eth_hash.auto import keccak

from server.db.redis_hotpath import redis_hotpath
from server.node.hsm_signer import node_signer

SPONSORSHIP_TIERS = {
    "T1": {
        "name": "High Priority Escrow Settlement",
        "description": "ArthenticEscrow.claim() and cancelListing()",
        "allowed_methods": ["claim", "cancelListing", "confirmDelivery"],
        "monthly_quota": 10,
        "max_gas_limit": 350000,
    },
    "T2": {
        "name": "Lifecycle & Curation",
        "description": "createListing(), updateCondition(), genesisMint(), replaceChip()",
        "allowed_methods": ["createListing", "updateCondition", "genesisMint", "replaceChip"],
        "monthly_quota": 25,
        "max_gas_limit": 450000,
    },
    "T3": {
        "name": "Public Verification Anchoring",
        "description": "ArthenticNFT.recordVerification()",
        "allowed_methods": ["recordVerification", "verifyLevel1", "verifyLevel2"],
        "monthly_quota": 5,
        "max_gas_limit": 200000,
    },
}

DEFAULT_ENTRYPOINT_V06 = "0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789"
DEFAULT_PAYMASTER_ADDRESS = "0x0000000000325602a77416A16136FDafd04b299f"


class PaymasterPolicyEngine:
    def __init__(
        self,
        chain_id: int = 84532,
        bundler_rpc_url: Optional[str] = None,
        paymaster_address: Optional[str] = None,
    ):
        self.chain_id = chain_id
        self.bundler_rpc_url = bundler_rpc_url or os.getenv("PAYMASTER_BUNDLER_RPC_URL", "")
        self.paymaster_address = paymaster_address or os.getenv(
            "ARTHENTIC_PAYMASTER_ADDRESS", DEFAULT_PAYMASTER_ADDRESS
        )

    def evaluate_sponsorship(
        self,
        wallet_address: str,
        method_name: str,
        user_roles: list,
    ) -> Dict[str, Any]:
        """
        Determines if a transaction is sponsored under T1, T2, or T3.
        Returns sponsorship verdict or K-04 fallback details.
        """
        norm_wallet = wallet_address.lower()
        matched_tier: Optional[str] = None

        for tier_id, tier in SPONSORSHIP_TIERS.items():
            if method_name in tier["allowed_methods"]:
                matched_tier = tier_id
                break

        if not matched_tier:
            return {
                "sponsored": False,
                "reason": f"Method '{method_name}' is not in any Paymaster sponsorship tier.",
                "fallback": "SELF_PAY_L2",
                "estimated_gas_usd": 0.01,
            }

        tier_config = SPONSORSHIP_TIERS[matched_tier]

        # Check Paymaster EntryPoint deposit status in Redis (Key #5 / K-03)
        pm_status = redis_hotpath.get_paymaster_balance(self.chain_id)
        if pm_status.get("status") == "empty":
            return {
                "sponsored": False,
                "reason": "Paymaster EntryPoint treasury is depleted. Triggering K-04 Self-Pay fallback.",
                "fallback": "SELF_PAY_L2",
                "estimated_gas_usd": 0.01,
            }

        # Check atomic monthly quota in Redis (Key #3 / K-02)
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        allowed, used, max_quota = redis_hotpath.check_and_increment_quota(
            wallet=norm_wallet,
            policy_id=matched_tier,
            period_key=current_month,
            max_quota=tier_config["monthly_quota"],
        )

        if not allowed:
            return {
                "sponsored": False,
                "reason": f"Monthly sponsored quota for {matched_tier} ({max_quota} txs) exhausted ({used}/{max_quota}).",
                "tier": matched_tier,
                "used_quota": used,
                "max_quota": max_quota,
                "fallback": "K04_SELF_PAY_MODAL",
                "estimated_gas_eth": "0.000005",
                "estimated_gas_usd": 0.015,
            }

        # Generate Paymaster sponsorship token
        paymaster_and_data = f"{self.paymaster_address}{secrets.token_hex(32)}"

        return {
            "sponsored": True,
            "tier": matched_tier,
            "tier_name": tier_config["name"],
            "used_quota": used,
            "max_quota": max_quota,
            "paymaster_and_data": paymaster_and_data,
            "paymasterAndData": paymaster_and_data,
            "gas_limit": tier_config["max_gas_limit"],
        }

    def sponsor_user_operation(
        self,
        user_op: Dict[str, Any],
        wallet_address: str,
        method_name: str,
        user_roles: List[str],
        entry_point: str = DEFAULT_ENTRYPOINT_V06,
    ) -> Dict[str, Any]:
        """
        ERC-4337 UserOperation Paymaster Sponsorship (K-01..K-05).
        1. Evaluates K-01 allow-list, K-02 monthly quota, and K-03 EntryPoint balance.
        2. If PAYMASTER_BUNDLER_RPC_URL is configured (Pimlico / Alchemy / Coinbase Paymaster),
           requests live pm_sponsorUserOperation JSON-RPC sponsorship.
        3. Otherwise signs the UserOperation digest via HsmProtocolNodeSigner and constructs
           deterministic ERC-4337 paymasterAndData.
        """
        verdict = self.evaluate_sponsorship(
            wallet_address=wallet_address,
            method_name=method_name,
            user_roles=user_roles,
        )
        if not verdict.get("sponsored"):
            return verdict

        # Try live ERC-4337 Paymaster Bundler RPC (pm_sponsorUserOperation) if configured
        if self.bundler_rpc_url:
            try:
                resp = httpx.post(
                    self.bundler_rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "pm_sponsorUserOperation",
                        "params": [
                            user_op,
                            entry_point,
                            {"sponsorshipPolicyId": f"arthentic_{verdict['tier'].lower()}"},
                        ],
                    },
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    rpc_result = resp.json().get("result")
                    if isinstance(rpc_result, dict) and rpc_result.get("paymasterAndData"):
                        return {
                            **verdict,
                            "paymasterAndData": rpc_result["paymasterAndData"],
                            "paymaster_and_data": rpc_result["paymasterAndData"],
                            "preVerificationGas": rpc_result.get("preVerificationGas", "0xc350"),
                            "verificationGasLimit": rpc_result.get("verificationGasLimit", "0x249f0"),
                            "callGasLimit": rpc_result.get("callGasLimit", hex(verdict["gas_limit"])),
                            "bundler_rpc_used": True,
                            "signature": rpc_result["paymasterAndData"],
                        }
            except Exception:
                pass

        # Deterministic KMS/HSM UserOperation signature for paymasterAndData
        canonical_op = json.dumps(user_op, sort_keys=True, separators=(",", ":")).encode("utf-8")
        op_digest = keccak(
            canonical_op + f":{self.chain_id}:{entry_point}:{verdict['tier']}".encode("utf-8")
        )
        sig_hex, kms_provider = node_signer.sign_raw_digest(op_digest)
        clean_sig = sig_hex[2:] if sig_hex.startswith("0x") else sig_hex
        paymaster_and_data = f"{self.paymaster_address}{clean_sig}"

        return {
            **verdict,
            "entry_point": entry_point,
            "paymasterAndData": paymaster_and_data,
            "paymaster_and_data": paymaster_and_data,
            "preVerificationGas": "0xc350",
            "verificationGasLimit": "0x249f0",
            "callGasLimit": hex(verdict["gas_limit"]),
            "bundler_rpc_used": False,
            "kms_provider": kms_provider,
            "signature": sig_hex,
        }


paymaster_engine = PaymasterPolicyEngine()
