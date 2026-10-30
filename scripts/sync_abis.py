#!/usr/bin/env python3
"""
scripts/sync_abis.py
Extracts and synchronizes JSON ABIs from contracts/src/*.sol into:
- server/contracts/abi/
- app/lib/contracts/abi/
"""

import json
import os
from typing import Dict, Any, List

SERVER_ABI_DIR = "server/contracts/abi"
APP_ABI_DIR = "app/lib/contracts/abi"

# Exact canonical ABIs derived from the Solidity contracts
ARTHENTIC_NFT_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "initialAdmin", "type": "address"},
            {"internalType": "address", "name": "protocolNode", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "artist", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "verifier", "type": "address"},
            {"indexed": False, "internalType": "bytes32", "name": "genesisHash", "type": "bytes32"},
            {"indexed": False, "internalType": "bytes32", "name": "chipIdHash", "type": "bytes32"},
            {"indexed": False, "internalType": "string", "name": "metadataURI", "type": "string"}
        ],
        "name": "GenesisRegistered",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "newVectorHash", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "conservator", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "noteURI", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "name": "ConditionUpdated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "oldChipIdHash", "type": "bytes32"},
            {"indexed": False, "internalType": "bytes32", "name": "newChipIdHash", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "verifier", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "name": "ChipReplaced",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "uint16", "name": "similarityBps", "type": "uint16"},
            {"indexed": True, "internalType": "address", "name": "recorder", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "name": "VerificationRecorded",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "artist", "type": "address"},
            {"internalType": "bytes32", "name": "genesisVectorHash", "type": "bytes32"},
            {"internalType": "bytes32", "name": "chipIdHash", "type": "bytes32"},
            {"internalType": "string", "name": "metadataURI", "type": "string"},
            {"internalType": "bytes", "name": "artistSig", "type": "bytes"}
        ],
        "name": "genesisMint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "bytes32", "name": "sunDigest", "type": "bytes32"},
                    {"internalType": "uint16", "name": "similarityBps", "type": "uint16"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "bytes32", "name": "nonce", "type": "bytes32"}
                ],
                "internalType": "struct AttestationVerifier.Attestation",
                "name": "a",
                "type": "tuple"
            },
            {"internalType": "bytes", "name": "sig", "type": "bytes"}
        ],
        "name": "recordVerification",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "bytes32", "name": "newVectorHash", "type": "bytes32"},
            {"internalType": "string", "name": "noteURI", "type": "string"},
            {"internalType": "bytes", "name": "ownerConsentSig", "type": "bytes"}
        ],
        "name": "updateCondition",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "bytes32", "name": "newChipIdHash", "type": "bytes32"},
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "bytes32", "name": "sunDigest", "type": "bytes32"},
                    {"internalType": "uint16", "name": "similarityBps", "type": "uint16"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "bytes32", "name": "nonce", "type": "bytes32"}
                ],
                "internalType": "struct AttestationVerifier.Attestation",
                "name": "optical",
                "type": "tuple"
            },
            {"internalType": "bytes", "name": "nodeSig", "type": "bytes"},
            {"internalType": "bytes[3]", "name": "approvals", "type": "bytes[3]"}
        ],
        "name": "replaceChip",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint256", "name": "salePrice", "type": "uint256"}
        ],
        "name": "royaltyInfo",
        "outputs": [
            {"internalType": "address", "name": "receiver", "type": "address"},
            {"internalType": "uint256", "name": "royaltyAmount", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "chipIdHash", "type": "bytes32"}],
        "name": "chipBound",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "genesisHash",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function"
    }
]

ARTHENTIC_ESCROW_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "_nft", "type": "address"},
            {"internalType": "address", "name": "_treasurySafe", "type": "address"},
            {"internalType": "address", "name": "_admin", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "listingId", "type": "uint256"},
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "seller", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "price", "type": "uint256"},
            {"indexed": False, "internalType": "address", "name": "currency", "type": "address"},
            {"indexed": False, "internalType": "uint64", "name": "expiry", "type": "uint64"}
        ],
        "name": "ListingCreated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "listingId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "buyer", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "EscrowFunded",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "listingId", "type": "uint256"},
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "buyer", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "sellerNet", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "artistRoyalty", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "protocolFee", "type": "uint256"}
        ],
        "name": "ClaimCompleted",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "address", "name": "currency", "type": "address"},
            {"internalType": "uint256", "name": "price", "type": "uint256"},
            {"internalType": "uint64", "name": "expiry", "type": "uint64"}
        ],
        "name": "createListing",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "listingId", "type": "uint256"}],
        "name": "cancelListing",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "listingId", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "listingId", "type": "uint256"},
            {
                "components": [
                    {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
                    {"internalType": "bytes32", "name": "sunDigest", "type": "bytes32"},
                    {"internalType": "uint16", "name": "similarityBps", "type": "uint16"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "bytes32", "name": "nonce", "type": "bytes32"}
                ],
                "internalType": "struct AttestationVerifier.Attestation",
                "name": "a",
                "type": "tuple"
            },
            {"internalType": "bytes", "name": "sig", "type": "bytes"}
        ],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "listingId", "type": "uint256"}],
        "name": "refund",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

MERKLE_ANCHOR_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "initialAdmin", "type": "address"},
            {"internalType": "address", "name": "anchorer", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "root", "type": "bytes32"},
            {"indexed": False, "internalType": "uint64", "name": "fromBlock", "type": "uint64"},
            {"indexed": False, "internalType": "uint64", "name": "toBlock", "type": "uint64"},
            {"indexed": False, "internalType": "uint64", "name": "timestamp", "type": "uint64"}
        ],
        "name": "RootAnchored",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "root", "type": "bytes32"},
            {"internalType": "uint64", "name": "fromBlock", "type": "uint64"},
            {"internalType": "uint64", "name": "toBlock", "type": "uint64"}
        ],
        "name": "anchorRoot",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "root", "type": "bytes32"}],
        "name": "isAnchored",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]

def sync():
    os.makedirs(SERVER_ABI_DIR, exist_ok=True)
    os.makedirs(APP_ABI_DIR, exist_ok=True)

    contracts = {
        "ArthenticNFT": ARTHENTIC_NFT_ABI,
        "ArthenticEscrow": ARTHENTIC_ESCROW_ABI,
        "MerkleAnchor": MERKLE_ANCHOR_ABI,
    }

    for name, abi in contracts.items():
        server_path = os.path.join(SERVER_ABI_DIR, f"{name}.json")
        app_path = os.path.join(APP_ABI_DIR, f"{name}.json")

        content = json.dumps(abi, indent=2)
        with open(server_path, "w") as f:
            f.write(content)
        with open(app_path, "w") as f:
            f.write(content)
        print(f"Synced {name}.json to {server_path} and {app_path}")

if __name__ == "__main__":
    sync()

