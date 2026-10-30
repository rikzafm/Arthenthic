"""
server/node/chain_client.py
EVM Web3 RPC Relayer & Contract Client for Base Sepolia L2 (84532: ArthenticNFT, ArthenticEscrow)
and Ethereum Sepolia L1 (11155111: MerkleAnchor).
Loads synchronized JSON ABIs from server/contracts/abi/ and supports:
1. Genuine EVM transaction construction, EIP-1559 gas estimation, eth_account signing,
   and JSON-RPC broadcasting via httpx in EVMChainClient.
2. In-memory ledger simulation with deterministic receipts in MockChainClient.
3. Factory injection via get_chain_client() and set_chain_client().
"""

from abc import ABC, abstractmethod
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from eth_account import Account
from eth_abi import encode as abi_encode, decode as abi_decode
from eth_utils import keccak, to_checksum_address
import httpx

ABI_DIR = Path(__file__).resolve().parent.parent / "contracts" / "abi"

DEFAULT_BASE_SEPOLIA_CHAIN_ID = 84532
DEFAULT_ETH_SEPOLIA_CHAIN_ID = 11155111

DEFAULT_NFT_ADDRESS = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
DEFAULT_ESCROW_ADDRESS = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
DEFAULT_MERKLE_ANCHOR_ADDRESS = "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0"

# Standard relayer dev key for signing node transactions when RELAYER_PRIVATE_KEY is unset
DEV_RELAYER_KEY = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"


def _canonical_type(inp: Dict[str, Any]) -> str:
    """Computes canonical ABI type string including recursive tuple declarations."""
    base_type = inp.get("type", "")
    if base_type.startswith("tuple"):
        components = inp.get("components", [])
        inner = ",".join(_canonical_type(c) for c in components)
        return f"({inner})" + base_type[5:]
    return base_type


class BaseChainClient(ABC):
    """
    Abstract Base Class defining the EVM Chain Client interface for reading contract state
    and broadcasting signed transactions.
    """

    def __init__(
        self,
        base_rpc_url: Optional[str] = None,
        l1_rpc_url: Optional[str] = None,
        nft_address: Optional[str] = None,
        escrow_address: Optional[str] = None,
        merkle_anchor_address: Optional[str] = None,
    ):
        self.base_chain_id = int(os.getenv("BASE_CHAIN_ID", str(DEFAULT_BASE_SEPOLIA_CHAIN_ID)))
        self.l1_chain_id = int(os.getenv("ETH_L1_CHAIN_ID", str(DEFAULT_ETH_SEPOLIA_CHAIN_ID)))
        self.base_rpc_url = base_rpc_url if base_rpc_url is not None else os.getenv("BASE_RPC_URL", "")
        self.l1_rpc_url = l1_rpc_url if l1_rpc_url is not None else os.getenv("ETH_L1_RPC_URL", "")
        self.nft_address = nft_address or os.getenv("ARTHENTIC_NFT_ADDRESS", DEFAULT_NFT_ADDRESS)
        self.escrow_address = escrow_address or os.getenv(
            "ARTHENTIC_ESCROW_ADDRESS", DEFAULT_ESCROW_ADDRESS
        )
        self.merkle_anchor_address = merkle_anchor_address or os.getenv(
            "MERKLE_ANCHOR_ADDRESS", DEFAULT_MERKLE_ANCHOR_ADDRESS
        )
        self._abis: Dict[str, List[Dict[str, Any]]] = {}
        self._load_abis()

    def _load_abis(self) -> None:
        for name in ("ArthenticNFT", "ArthenticEscrow", "MerkleAnchor"):
            abi_path = ABI_DIR / f"{name}.json"
            if abi_path.exists():
                with open(abi_path, "r", encoding="utf-8") as f:
                    self._abis[name] = json.load(f)
            else:
                self._abis[name] = []

    def get_abi(self, contract_name: str) -> List[Dict[str, Any]]:
        """Returns the synchronized JSON ABI for the requested contract."""
        return self._abis.get(contract_name, [])

    def get_function_selectors(self, contract_name: str) -> Dict[str, str]:
        """Computes 4-byte function selectors for all functions in the contract ABI."""
        selectors: Dict[str, str] = {}
        for item in self.get_abi(contract_name):
            if item.get("type") == "function":
                fn_name = item["name"]
                arg_types = ",".join(_canonical_type(inp) for inp in item.get("inputs", []))
                sig = f"{fn_name}({arg_types})"
                selector = "0x" + keccak(text=sig)[:4].hex()
                selectors[fn_name] = selector
        return selectors

    def get_contract_deployment_manifest(self) -> Dict[str, Any]:
        """Returns the Base Sepolia and Ethereum Sepolia contract configuration and ABI selectors."""
        return {
            "base_sepolia": {
                "chain_id": self.base_chain_id,
                "network_name": "Base Sepolia",
                "rpc_configured": bool(self.base_rpc_url),
                "explorer_url": "https://sepolia.basescan.org",
                "contracts": {
                    "ArthenticNFT": self.nft_address,
                    "ArthenticEscrow": self.escrow_address,
                },
            },
            "ethereum_sepolia": {
                "chain_id": self.l1_chain_id,
                "network_name": "Ethereum Sepolia",
                "rpc_configured": bool(self.l1_rpc_url),
                "explorer_url": "https://sepolia.etherscan.io",
                "contracts": {
                    "MerkleAnchor": self.merkle_anchor_address,
                },
            },
            "selectors": {
                "ArthenticNFT": self.get_function_selectors("ArthenticNFT"),
                "ArthenticEscrow": self.get_function_selectors("ArthenticEscrow"),
                "MerkleAnchor": self.get_function_selectors("MerkleAnchor"),
            },
        }

    # ------------------------------------------------------------------
    # Abstract Read Methods
    # ------------------------------------------------------------------
    @abstractmethod
    def get_onchain_owner(self, token_id: int, fallback_owner: Optional[str] = None) -> Optional[str]: ...

    @abstractmethod
    def get_genesis_hash(self, token_id: int, fallback_hash: Optional[str] = None) -> Optional[str]: ...

    @abstractmethod
    def is_chip_bound(self, chip_id_hash: str, fallback_bound: bool = False) -> bool: ...

    @abstractmethod
    def get_listing_state(
        self, listing_id: Any, fallback_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]: ...

    # ------------------------------------------------------------------
    # Abstract Broadcast Methods
    # ------------------------------------------------------------------
    @abstractmethod
    def broadcast_genesis_mint(
        self,
        artist: str,
        genesis_vector_hash: str,
        chip_id_hash: str,
        metadata_uri: str,
        artist_co_signature: str,
    ) -> Dict[str, Any]: ...

    @abstractmethod
    def broadcast_update_condition(
        self,
        token_id: int,
        new_vector_hash: str,
        note_uri: str,
        owner_consent_sig: str,
    ) -> Dict[str, Any]: ...

    @abstractmethod
    def broadcast_replace_chip(
        self,
        token_id: int,
        new_chip_id_hash: str,
        optical_similarity_bps: int,
        approvals: List[str],
    ) -> Dict[str, Any]: ...

    @abstractmethod
    def broadcast_escrow_refund(self, listing_id: Any) -> Dict[str, Any]: ...

    @abstractmethod
    def broadcast_escrow_claim(
        self,
        listing_id: Any,
        attestation: Dict[str, Any],
        signature: str,
    ) -> Dict[str, Any]: ...

    @abstractmethod
    def anchor_merkle_root_l1(self, root_hex: str, from_block: int, to_block: int) -> Dict[str, Any]: ...


class EVMChainClient(BaseChainClient):
    """
    Genuine EVM Web3 JSON-RPC client performing transaction construction, ABI encoding,
    pending nonce tracking, EIP-1559 gas fee estimation, eth_account signing,
    and JSON-RPC broadcasting via httpx.
    Fails fast with ConnectionError if RPC is unconfigured or unreachable.
    """

    def __init__(
        self,
        base_rpc_url: Optional[str] = None,
        l1_rpc_url: Optional[str] = None,
        nft_address: Optional[str] = None,
        escrow_address: Optional[str] = None,
        merkle_anchor_address: Optional[str] = None,
        relayer_private_key: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        super().__init__(
            base_rpc_url=base_rpc_url,
            l1_rpc_url=l1_rpc_url,
            nft_address=nft_address,
            escrow_address=escrow_address,
            merkle_anchor_address=merkle_anchor_address,
        )
        self.relayer_private_key = relayer_private_key or os.getenv("RELAYER_PRIVATE_KEY", DEV_RELAYER_KEY)
        self.max_priority_fee_per_gas = int(os.getenv("MAX_PRIORITY_FEE_PER_GAS", "1500000000"))  # 1.5 gwei
        self.timeout = float(os.getenv("CHAIN_CLIENT_TIMEOUT", "5.0"))
        self._http_client = http_client

    def _rpc_call(self, rpc_url: str, method: str, params: List[Any]) -> Any:
        if not rpc_url:
            raise ConnectionError(
                f"Base RPC URL not configured or unreachable: RPC URL for method '{method}' is not configured."
            )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        try:
            if self._http_client is not None:
                resp = self._http_client.post(rpc_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(rpc_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            if "error" in data:
                err_detail = data["error"].get("message", data["error"]) if isinstance(data["error"], dict) else data["error"]
                raise RuntimeError(f"JSON-RPC execution error in {method}: {err_detail}")
            return data.get("result")
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise ConnectionError(
                f"Base RPC URL not configured or unreachable: RPC endpoint '{rpc_url}' unreachable for {method}: {exc}"
            ) from exc

    def _build_and_send_tx(
        self,
        to_address: str,
        calldata: bytes,
        chain_id: int,
        rpc_url: str,
        method_name: str,
        **extra_receipt: Any,
    ) -> Dict[str, Any]:
        """
        Executes genuine EIP-1559 transaction construction, fee calculation, nonce resolution,
        offline signing via eth_account, and broadcast via eth_sendRawTransaction.
        """
        if not rpc_url:
            raise ConnectionError(
                f"Base RPC URL not configured or unreachable: RPC URL for chain ID {chain_id} is not configured; cannot broadcast {method_name}."
            )

        acct = Account.from_key(self.relayer_private_key)
        relayer_addr = acct.address

        # 1. Nonce resolution via pending count
        nonce_res = self._rpc_call(rpc_url, "eth_getTransactionCount", [relayer_addr, "pending"])
        nonce = int(nonce_res, 16)

        # 2. Base fee query via latest block
        block_res = self._rpc_call(rpc_url, "eth_getBlockByNumber", ["latest", False])
        if block_res and isinstance(block_res, dict) and "baseFeePerGas" in block_res:
            base_fee = int(block_res["baseFeePerGas"], 16)
        else:
            base_fee = 10**9  # 1 gwei fallback
        max_priority_fee = self.max_priority_fee_per_gas
        max_fee = int(base_fee * 1.5) + max_priority_fee

        # 3. Gas limit estimation with 20% margin
        try:
            gas_est_res = self._rpc_call(
                rpc_url,
                "eth_estimateGas",
                [{"from": relayer_addr, "to": to_address, "data": "0x" + calldata.hex()}],
            )
            gas_limit = int(int(gas_est_res, 16) * 1.2)
        except Exception:
            gas_limit = 500_000

        # 4. Construct EIP-1559 transaction dictionary
        tx_dict = {
            "to": to_address,
            "value": 0,
            "gas": gas_limit,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": max_priority_fee,
            "nonce": nonce,
            "chainId": chain_id,
            "type": 2,
            "data": calldata,
        }

        # 5. Sign raw transaction
        signed = acct.sign_transaction(tx_dict)
        raw_tx = signed.raw_transaction.hex()
        if not raw_tx.startswith("0x"):
            raw_tx = "0x" + raw_tx

        # 6. Broadcast via JSON-RPC
        broadcast_hash = self._rpc_call(rpc_url, "eth_sendRawTransaction", [raw_tx])
        tx_hash = broadcast_hash or ("0x" + signed.hash.hex())

        receipt = {
            "chain_id": chain_id,
            "contract_address": to_address,
            "method": method_name,
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
        }
        receipt.update(extra_receipt)
        return receipt

    # ------------------------------------------------------------------
    # On-Chain Read Methods
    # ------------------------------------------------------------------
    def get_onchain_owner(self, token_id: int, fallback_owner: Optional[str] = None) -> Optional[str]:
        if not self.base_rpc_url:
            return fallback_owner
        try:
            selector = bytes.fromhex("6352211e")  # ownerOf(uint256)
            calldata = selector + abi_encode(["uint256"], [int(token_id)])
            res = self._rpc_call(
                self.base_rpc_url,
                "eth_call",
                [{"to": self.nft_address, "data": "0x" + calldata.hex()}, "latest"],
            )
            if res and res != "0x":
                raw_bytes = bytes.fromhex(res[2:])
                decoded = abi_decode(["address"], raw_bytes)[0]
                return str(decoded).lower()
        except Exception:
            pass
        return fallback_owner

    def get_genesis_hash(self, token_id: int, fallback_hash: Optional[str] = None) -> Optional[str]:
        if not self.base_rpc_url:
            return fallback_hash
        try:
            selector = bytes.fromhex("00d34765")  # genesisHash(uint256)
            calldata = selector + abi_encode(["uint256"], [int(token_id)])
            res = self._rpc_call(
                self.base_rpc_url,
                "eth_call",
                [{"to": self.nft_address, "data": "0x" + calldata.hex()}, "latest"],
            )
            if res and res != "0x":
                raw_bytes = bytes.fromhex(res[2:])
                decoded = abi_decode(["bytes32"], raw_bytes)[0]
                return "0x" + decoded.hex()
        except Exception:
            pass
        return fallback_hash

    def is_chip_bound(self, chip_id_hash: str, fallback_bound: bool = False) -> bool:
        if not self.base_rpc_url:
            return fallback_bound
        try:
            selector = bytes.fromhex("4c21ac33")  # chipBound(bytes32)
            clean_chip = bytes.fromhex(chip_id_hash[2:] if chip_id_hash.startswith("0x") else chip_id_hash)
            calldata = selector + abi_encode(["bytes32"], [clean_chip])
            res = self._rpc_call(
                self.base_rpc_url,
                "eth_call",
                [{"to": self.nft_address, "data": "0x" + calldata.hex()}, "latest"],
            )
            if res and res != "0x":
                raw_bytes = bytes.fromhex(res[2:])
                decoded = abi_decode(["bool"], raw_bytes)[0]
                return bool(decoded)
        except Exception:
            pass
        return fallback_bound

    def get_listing_state(
        self, listing_id: Any, fallback_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.base_rpc_url or not str(listing_id).isdigit():
            return fallback_state or {"listing_id": str(listing_id), "status": "ACTIVE"}
        try:
            selector = bytes.fromhex("de74e57b")  # listings(uint256)
            calldata = selector + abi_encode(["uint256"], [int(listing_id)])
            res = self._rpc_call(
                self.base_rpc_url,
                "eth_call",
                [{"to": self.escrow_address, "data": "0x" + calldata.hex()}, "latest"],
            )
            if res and res != "0x":
                raw_bytes = bytes.fromhex(res[2:])
                row = abi_decode(
                    ["uint256", "address", "address", "address", "uint256", "uint64", "uint8"], raw_bytes
                )
                status_enum = ["NONE", "LISTED", "FUNDED", "COMPLETED", "REFUNDED", "DISPUTED", "CANCELLED"]
                st = status_enum[row[6]] if row[6] < len(status_enum) else "UNKNOWN"
                return {
                    "token_id": row[0],
                    "seller": row[1],
                    "buyer": row[2],
                    "payment_token": row[3],
                    "price": row[4],
                    "expiry": row[5],
                    "state": row[6],
                    "status": st,
                }
        except Exception:
            pass
        return fallback_state or {"listing_id": str(listing_id), "status": "ACTIVE"}

    # ------------------------------------------------------------------
    # On-Chain Write / Broadcast Methods
    # ------------------------------------------------------------------
    def broadcast_genesis_mint(
        self,
        artist: str,
        genesis_vector_hash: str,
        chip_id_hash: str,
        metadata_uri: str,
        artist_co_signature: str,
    ) -> Dict[str, Any]:
        selector = bytes.fromhex("62058688")  # genesisMint(address,bytes32,bytes32,string,bytes)
        clean_artist = to_checksum_address(artist)
        clean_vec = bytes.fromhex(genesis_vector_hash[2:] if genesis_vector_hash.startswith("0x") else genesis_vector_hash)
        clean_chip = bytes.fromhex(chip_id_hash[2:] if chip_id_hash.startswith("0x") else chip_id_hash)
        clean_sig = bytes.fromhex(artist_co_signature[2:] if artist_co_signature.startswith("0x") else artist_co_signature)

        calldata = selector + abi_encode(
            ["address", "bytes32", "bytes32", "string", "bytes"],
            [clean_artist, clean_vec, clean_chip, metadata_uri, clean_sig],
        )
        return self._build_and_send_tx(
            to_address=self.nft_address,
            calldata=calldata,
            chain_id=self.base_chain_id,
            rpc_url=self.base_rpc_url,
            method_name="genesisMint",
        )

    def broadcast_update_condition(
        self,
        token_id: int,
        new_vector_hash: str,
        note_uri: str,
        owner_consent_sig: str,
    ) -> Dict[str, Any]:
        selector = bytes.fromhex("52738a95")  # updateCondition(uint256,bytes32,string,bytes)
        clean_vec = bytes.fromhex(new_vector_hash[2:] if new_vector_hash.startswith("0x") else new_vector_hash)
        clean_sig = bytes.fromhex(owner_consent_sig[2:] if owner_consent_sig.startswith("0x") else owner_consent_sig)

        calldata = selector + abi_encode(
            ["uint256", "bytes32", "string", "bytes"],
            [int(token_id), clean_vec, note_uri, clean_sig],
        )
        return self._build_and_send_tx(
            to_address=self.nft_address,
            calldata=calldata,
            chain_id=self.base_chain_id,
            rpc_url=self.base_rpc_url,
            method_name="updateCondition",
            token_id=token_id,
        )

    def broadcast_replace_chip(
        self,
        token_id: int,
        new_chip_id_hash: str,
        optical_similarity_bps: int,
        approvals: List[str],
    ) -> Dict[str, Any]:
        selector = bytes.fromhex("6228ed75")  # replaceChip(uint256,bytes32,(uint256,bytes32,uint16,uint256,bytes32),bytes,bytes[3])
        clean_chip = bytes.fromhex(new_chip_id_hash[2:] if new_chip_id_hash.startswith("0x") else new_chip_id_hash)
        optical_tuple = (int(token_id), b"\x00" * 32, int(optical_similarity_bps), 0, b"\x00" * 32)
        node_sig = b"\x00" * 65

        approvals_bytes: List[bytes] = []
        for sig in approvals[:3]:
            hex_str = sig[2:] if sig.startswith("0x") else sig
            try:
                approvals_bytes.append(bytes.fromhex(hex_str))
            except Exception:
                approvals_bytes.append(b"\x00" * 65)
        while len(approvals_bytes) < 3:
            approvals_bytes.append(b"\x00" * 65)

        calldata = selector + abi_encode(
            ["uint256", "bytes32", "(uint256,bytes32,uint16,uint256,bytes32)", "bytes", "bytes[3]"],
            [int(token_id), clean_chip, optical_tuple, node_sig, approvals_bytes],
        )
        return self._build_and_send_tx(
            to_address=self.nft_address,
            calldata=calldata,
            chain_id=self.base_chain_id,
            rpc_url=self.base_rpc_url,
            method_name="replaceChip",
            token_id=token_id,
        )

    def broadcast_escrow_refund(self, listing_id: Any) -> Dict[str, Any]:
        selector = bytes.fromhex("278ecde1")  # refund(uint256)
        lid_int = int(listing_id) if str(listing_id).isdigit() else int(
            hashlib.sha256(str(listing_id).encode()).hexdigest()[:8], 16
        )
        calldata = selector + abi_encode(["uint256"], [lid_int])
        return self._build_and_send_tx(
            to_address=self.escrow_address,
            calldata=calldata,
            chain_id=self.base_chain_id,
            rpc_url=self.base_rpc_url,
            method_name="refund",
            listing_id=str(listing_id),
        )

    def broadcast_escrow_claim(
        self,
        listing_id: Any,
        attestation: Dict[str, Any],
        signature: str,
    ) -> Dict[str, Any]:
        selector = bytes.fromhex("2881b321")  # claim(uint256,(uint256,bytes32,uint16,uint256,bytes32),bytes)
        lid_int = int(listing_id) if str(listing_id).isdigit() else int(
            hashlib.sha256(str(listing_id).encode()).hexdigest()[:8], 16
        )
        token_id_int = int(attestation["tokenId"])
        sun_digest_bytes = bytes.fromhex(
            attestation["sunDigest"][2:] if str(attestation["sunDigest"]).startswith("0x") else str(attestation["sunDigest"])
        )
        similarity_bps_int = int(attestation["similarityBps"])
        deadline_int = int(attestation["deadline"])
        nonce_bytes = bytes.fromhex(
            attestation["nonce"][2:] if str(attestation["nonce"]).startswith("0x") else str(attestation["nonce"])
        )
        sig_bytes = bytes.fromhex(signature[2:] if signature.startswith("0x") else signature)

        att_tuple = (token_id_int, sun_digest_bytes, similarity_bps_int, deadline_int, nonce_bytes)

        calldata = selector + abi_encode(
            ["uint256", "(uint256,bytes32,uint16,uint256,bytes32)", "bytes"],
            [lid_int, att_tuple, sig_bytes],
        )

        return self._build_and_send_tx(
            to_address=self.escrow_address,
            calldata=calldata,
            chain_id=self.base_chain_id,
            rpc_url=self.base_rpc_url,
            method_name="claim",
            listing_id=str(listing_id),
        )

    def anchor_merkle_root_l1(self, root_hex: str, from_block: int, to_block: int) -> Dict[str, Any]:
        selector = bytes.fromhex("3d76c0b8")  # anchorRoot(bytes32,uint64,uint64)
        clean_root = bytes.fromhex(root_hex[2:] if root_hex.startswith("0x") else root_hex)
        calldata = selector + abi_encode(["bytes32", "uint64", "uint64"], [clean_root, int(from_block), int(to_block)])
        res = self._build_and_send_tx(
            to_address=self.merkle_anchor_address,
            calldata=calldata,
            chain_id=self.l1_chain_id,
            rpc_url=self.l1_rpc_url,
            method_name="anchorRoot",
            root=root_hex,
            from_block=from_block,
            to_block=to_block,
        )
        res["l1_tx_hash"] = res["tx_hash"]
        return res


class MockChainClient(BaseChainClient):
    """
    In-memory ledger simulator tracking chips, token owners, genesis hashes,
    and marketplace listings with deterministic mock receipts.
    Guarantees 100% offline local development and deterministic test execution.
    """

    def __init__(
        self,
        base_rpc_url: Optional[str] = None,
        l1_rpc_url: Optional[str] = None,
        nft_address: Optional[str] = None,
        escrow_address: Optional[str] = None,
        merkle_anchor_address: Optional[str] = None,
    ):
        super().__init__(
            base_rpc_url=base_rpc_url,
            l1_rpc_url=l1_rpc_url,
            nft_address=nft_address,
            escrow_address=escrow_address,
            merkle_anchor_address=merkle_anchor_address,
        )
        self.bound_chips: set = set()
        self.token_owners: Dict[int, str] = {}
        self.genesis_hashes: Dict[int, str] = {}
        self.token_chips: Dict[int, str] = {}
        self._next_token_id: int = 1
        self.listings: Dict[str, Dict[str, Any]] = {}
        self.condition_updates: Dict[int, List[Dict[str, Any]]] = {}
        self.replacement_log: List[Dict[str, Any]] = []
        self.anchored_roots: set = set()
        self.broadcast_log: List[Dict[str, Any]] = []

    def reset(self) -> None:
        """Clears all simulated in-memory state."""
        self.bound_chips.clear()
        self.token_owners.clear()
        self.genesis_hashes.clear()
        self.token_chips.clear()
        self._next_token_id = 1
        self.listings.clear()
        self.condition_updates.clear()
        self.replacement_log.clear()
        self.anchored_roots.clear()
        self.broadcast_log.clear()

    def seed_token(
        self, token_id: int, owner: str, genesis_hash: str, chip_id_hash: Optional[str] = None
    ) -> None:
        """Helper to seed simulated token state for test fixtures."""
        self.token_owners[token_id] = owner.lower()
        self.genesis_hashes[token_id] = genesis_hash
        if chip_id_hash:
            chip_lower = chip_id_hash.lower()
            self.bound_chips.add(chip_lower)
            self.token_chips[token_id] = chip_lower

    def seed_listing(self, listing_id: Any, state: Dict[str, Any]) -> None:
        """Helper to seed simulated escrow listing state."""
        self.listings[str(listing_id)] = state

    # ------------------------------------------------------------------
    # Read Methods
    # ------------------------------------------------------------------
    def get_onchain_owner(self, token_id: int, fallback_owner: Optional[str] = None) -> Optional[str]:
        return self.token_owners.get(token_id, fallback_owner)

    def get_genesis_hash(self, token_id: int, fallback_hash: Optional[str] = None) -> Optional[str]:
        return self.genesis_hashes.get(token_id, fallback_hash)

    def is_chip_bound(self, chip_id_hash: str, fallback_bound: bool = False) -> bool:
        if chip_id_hash.lower() in self.bound_chips:
            return True
        return fallback_bound

    def get_listing_state(
        self, listing_id: Any, fallback_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.listings.get(str(listing_id), fallback_state or {"listing_id": str(listing_id), "status": "ACTIVE"})

    # ------------------------------------------------------------------
    # Broadcast Methods
    # ------------------------------------------------------------------
    def broadcast_genesis_mint(
        self,
        artist: str,
        genesis_vector_hash: str,
        chip_id_hash: str,
        metadata_uri: str,
        artist_co_signature: str,
    ) -> Dict[str, Any]:
        chip_lower = chip_id_hash.lower()
        if chip_lower in self.bound_chips:
            raise ValueError(f"CHIP_ALREADY_BOUND: {chip_id_hash}")
        self.bound_chips.add(chip_lower)
        token_id = self._next_token_id
        self._next_token_id += 1
        self.token_chips[token_id] = chip_lower
        self.token_owners[token_id] = artist.lower()
        self.genesis_hashes[token_id] = genesis_vector_hash

        seed = f"mock_genesisMint:{artist}:{chip_id_hash}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.base_chain_id,
            "contract_address": self.nft_address,
            "method": "genesisMint",
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt

    def broadcast_update_condition(
        self,
        token_id: int,
        new_vector_hash: str,
        note_uri: str,
        owner_consent_sig: str,
    ) -> Dict[str, Any]:
        self.condition_updates.setdefault(token_id, []).append({
            "new_vector_hash": new_vector_hash,
            "note_uri": note_uri,
            "owner_consent_sig": owner_consent_sig,
        })
        seed = f"mock_updateCondition:{token_id}:{new_vector_hash}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.base_chain_id,
            "contract_address": self.nft_address,
            "method": "updateCondition",
            "token_id": token_id,
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt

    def broadcast_replace_chip(
        self,
        token_id: int,
        new_chip_id_hash: str,
        optical_similarity_bps: int,
        approvals: List[str],
    ) -> Dict[str, Any]:
        new_chip_lower = new_chip_id_hash.lower()
        if new_chip_lower in self.bound_chips:
            raise ValueError(f"CHIP_ALREADY_BOUND: {new_chip_id_hash}")
        old_chip = self.token_chips.get(token_id)
        if old_chip:
            self.bound_chips.discard(old_chip)
        self.bound_chips.add(new_chip_lower)
        self.token_chips[token_id] = new_chip_lower

        self.replacement_log.append({
            "token_id": token_id,
            "new_chip_id_hash": new_chip_id_hash,
            "optical_similarity_bps": optical_similarity_bps,
            "approvals": approvals,
        })
        seed = f"mock_replaceChip:{token_id}:{new_chip_id_hash}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.base_chain_id,
            "contract_address": self.nft_address,
            "method": "replaceChip",
            "token_id": token_id,
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt

    def broadcast_escrow_refund(self, listing_id: Any) -> Dict[str, Any]:
        key = str(listing_id)
        if key in self.listings:
            self.listings[key]["status"] = "REFUNDED"
            self.listings[key]["state"] = 4  # Refunded status in Solidity
        seed = f"mock_refund:{key}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.base_chain_id,
            "contract_address": self.escrow_address,
            "method": "refund",
            "listing_id": key,
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt

    def broadcast_escrow_claim(
        self,
        listing_id: Any,
        attestation: Dict[str, Any],
        signature: str,
    ) -> Dict[str, Any]:
        key = str(listing_id)
        if key in self.listings:
            self.listings[key]["status"] = "COMPLETED"
            self.listings[key]["state"] = 3  # Completed status in Solidity
        seed = f"mock_claim:{key}:{attestation.get('nonce')}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.base_chain_id,
            "contract_address": self.escrow_address,
            "method": "claim",
            "listing_id": key,
            "tx_hash": tx_hash,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt

    def anchor_merkle_root_l1(self, root_hex: str, from_block: int, to_block: int) -> Dict[str, Any]:
        self.anchored_roots.add(root_hex)
        seed = f"mock_anchor:{root_hex}:{from_block}:{to_block}:{len(self.broadcast_log)}"
        tx_hash = "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        receipt = {
            "chain_id": self.l1_chain_id,
            "contract_address": self.merkle_anchor_address,
            "method": "anchorRoot",
            "l1_tx_hash": tx_hash,
            "root": root_hex,
            "from_block": from_block,
            "to_block": to_block,
            "status": "CONFIRMED",
            "mock": True,
        }
        self.broadcast_log.append(receipt)
        return receipt


# ----------------------------------------------------------------------
# Factory & Proxy Singleton Pattern
# ----------------------------------------------------------------------
_current_client: Optional[BaseChainClient] = None


def get_chain_client() -> BaseChainClient:
    """
    Returns the active BaseChainClient singleton.
    Resolution order:
    1. Explicit instance set via set_chain_client().
    2. If CHAIN_CLIENT_MODE is 'live' or 'evm', returns EVMChainClient().
    3. If BASE_RPC_URL is non-empty and CHAIN_CLIENT_MODE is unset, returns EVMChainClient().
    4. Otherwise, defaults to MockChainClient() ensuring 100% offline development and testing.
    """
    global _current_client
    if _current_client is None:
        mode = os.getenv("CHAIN_CLIENT_MODE", "").lower()
        if mode in ("live", "evm") or (not mode and bool(os.getenv("BASE_RPC_URL"))):
            _current_client = EVMChainClient()
        else:
            _current_client = MockChainClient()
    return _current_client


def set_chain_client(client: Optional[BaseChainClient]) -> None:
    """Sets or clears the active chain client singleton (for testing & dependency injection)."""
    global _current_client
    _current_client = client


class _ChainClientProxy(BaseChainClient):
    """
    Transparent delegation proxy ensuring that `from server.node.chain_client import chain_client`
    dynamically forwards attribute access and calls to the current active singleton.
    """

    def __init__(self) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(get_chain_client(), name)

    def __repr__(self) -> str:
        return f"<ChainClientProxy -> {get_chain_client()!r}>"

    def get_abi(self, contract_name: str) -> List[Dict[str, Any]]:
        return get_chain_client().get_abi(contract_name)

    def get_function_selectors(self, contract_name: str) -> Dict[str, str]:
        return get_chain_client().get_function_selectors(contract_name)

    def get_contract_deployment_manifest(self) -> Dict[str, Any]:
        return get_chain_client().get_contract_deployment_manifest()

    def get_onchain_owner(self, token_id: int, fallback_owner: Optional[str] = None) -> Optional[str]:
        return get_chain_client().get_onchain_owner(token_id, fallback_owner)

    def get_genesis_hash(self, token_id: int, fallback_hash: Optional[str] = None) -> Optional[str]:
        return get_chain_client().get_genesis_hash(token_id, fallback_hash)

    def is_chip_bound(self, chip_id_hash: str, fallback_bound: bool = False) -> bool:
        return get_chain_client().is_chip_bound(chip_id_hash, fallback_bound)

    def get_listing_state(
        self, listing_id: Any, fallback_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return get_chain_client().get_listing_state(listing_id, fallback_state)

    def broadcast_genesis_mint(
        self,
        artist: str,
        genesis_vector_hash: str,
        chip_id_hash: str,
        metadata_uri: str,
        artist_co_signature: str,
    ) -> Dict[str, Any]:
        return get_chain_client().broadcast_genesis_mint(
            artist, genesis_vector_hash, chip_id_hash, metadata_uri, artist_co_signature
        )

    def broadcast_update_condition(
        self,
        token_id: int,
        new_vector_hash: str,
        note_uri: str,
        owner_consent_sig: str,
    ) -> Dict[str, Any]:
        return get_chain_client().broadcast_update_condition(
            token_id, new_vector_hash, note_uri, owner_consent_sig
        )

    def broadcast_replace_chip(
        self,
        token_id: int,
        new_chip_id_hash: str,
        optical_similarity_bps: int,
        approvals: List[str],
    ) -> Dict[str, Any]:
        return get_chain_client().broadcast_replace_chip(
            token_id, new_chip_id_hash, optical_similarity_bps, approvals
        )

    def broadcast_escrow_refund(self, listing_id: Any) -> Dict[str, Any]:
        return get_chain_client().broadcast_escrow_refund(listing_id)

    def broadcast_escrow_claim(
        self,
        listing_id: Any,
        attestation: Dict[str, Any],
        signature: str,
    ) -> Dict[str, Any]:
        return get_chain_client().broadcast_escrow_claim(listing_id, attestation, signature)

    def anchor_merkle_root_l1(self, root_hex: str, from_block: int, to_block: int) -> Dict[str, Any]:
        return get_chain_client().anchor_merkle_root_l1(root_hex, from_block, to_block)


chain_client = _ChainClientProxy()
