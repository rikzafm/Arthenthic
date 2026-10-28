"""
EIP-712 Attestation Signer for Arthentic.
Matches the on-chain Solidity struct:
Attestation {
    uint256 tokenId;
    bytes32 sunDigest;
    uint16 similarityBps;
    uint256 deadline;
    bytes32 nonce;
}
"""

import time
import secrets
import hashlib
from typing import Dict, Any, Tuple
from eth_account import Account
from eth_account.messages import encode_typed_data

# Well-known test signer for prototype (NEVER use in real production)
TEST_SIGNER_PRIVATE_KEY = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
TEST_SIGNER_ACCOUNT = Account.from_key(TEST_SIGNER_PRIVATE_KEY)

CHAIN_ID = 84532  # Base Sepolia
VERIFYING_CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

ATTESTATION_DOMAIN = {
    "name": "ArthenticAttestation",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": VERIFYING_CONTRACT
}

ATTESTATION_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "Attestation": [
        {"name": "tokenId", "type": "uint256"},
        {"name": "sunDigest", "type": "bytes32"},
        {"name": "similarityBps", "type": "uint16"},
        {"name": "deadline", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"}
    ]
}

class AttestationSigner:
    def __init__(self, private_key: str = TEST_SIGNER_PRIVATE_KEY):
        self.account = Account.from_key(private_key)
        self.used_nonces = set()

    @property
    def address(self) -> str:
        return self.account.address

    def compute_sun_digest(self, uid: str, ctr: int, cmac: str) -> str:
        """Calculate bytes32 digest from SUN params"""
        payload = f"{uid}:{ctr}:{cmac}".encode("utf-8")
        return "0x" + hashlib.sha256(payload).hexdigest()

    def create_attestation(
        self,
        token_id: int,
        sun_digest: str,
        similarity_bps: int,
        validity_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Create and sign an EIP-712 attestation.
        """
        deadline = int(time.time()) + validity_seconds
        nonce = "0x" + secrets.token_hex(32)
        while nonce in self.used_nonces:
            nonce = "0x" + secrets.token_hex(32)
        self.used_nonces.add(nonce)

        message = {
            "tokenId": token_id,
            "sunDigest": sun_digest,
            "similarityBps": similarity_bps,
            "deadline": deadline,
            "nonce": nonce
        }

        signable = encode_typed_data(
            domain_data=ATTESTATION_DOMAIN,
            message_types={"Attestation": ATTESTATION_TYPES["Attestation"]},
            message_data=message
        )
        signed = self.account.sign_message(signable)
        signature = signed.signature.hex()

        return {
            "tokenId": str(token_id),
            "sunDigest": sun_digest,
            "similarityBps": similarity_bps,
            "deadline": deadline,
            "nonce": nonce,
            "signer": self.address,
            "signature": "0x" + signature if not signature.startswith("0x") else signature
        }

attestation_signer = AttestationSigner()

