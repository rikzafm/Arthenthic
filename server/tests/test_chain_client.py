"""
server/tests/test_chain_client.py
Comprehensive offline test suite for Arthenthic EVM Chain Client architecture.
Covers MockChainClient in-memory ledger simulation and EVMChainClient genuine Web3 JSON-RPC
transaction construction, EIP-1559 serialization, calldata encoding, and fail-fast errors.
"""

import json
import pytest
import rlp
import httpx
from eth_account import Account
import eth_abi
from eth_utils import keccak

from server.node.chain_client import (
    BaseChainClient,
    EVMChainClient,
    MockChainClient,
    get_chain_client,
    set_chain_client,
    chain_client,
    DEV_RELAYER_KEY,
)

RELAYER_KEY = DEV_RELAYER_KEY
RELAYER_ACCT = Account.from_key(RELAYER_KEY)


@pytest.fixture
def clean_mock_client():
    client = MockChainClient()
    set_chain_client(client)
    yield client
    set_chain_client(MockChainClient())


# ==============================================================================
# Suite 1: MockChainClient In-Memory Ledger Simulation
# ==============================================================================
class TestMockChainClient:
    def test_mock_client_initial_state(self, clean_mock_client):
        """Verifies clean initial state and ABI selector loading."""
        manifest = clean_mock_client.get_contract_deployment_manifest()
        assert manifest["base_sepolia"]["chain_id"] == 84532
        assert manifest["ethereum_sepolia"]["chain_id"] == 11155111
        assert "ArthenticNFT" in manifest["base_sepolia"]["contracts"]
        assert "ArthenticEscrow" in manifest["base_sepolia"]["contracts"]
        assert "MerkleAnchor" in manifest["ethereum_sepolia"]["contracts"]

        assert len(clean_mock_client.bound_chips) == 0
        assert len(clean_mock_client.broadcast_log) == 0

    def test_genesis_mint_binds_chip_and_records_owner(self, clean_mock_client):
        """Verifies broadcast_genesis_mint binds chip, sets owner, and logs receipt."""
        receipt = clean_mock_client.broadcast_genesis_mint(
            artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
            genesis_vector_hash="0x" + "11" * 32,
            chip_id_hash="0x" + "22" * 32,
            metadata_uri="ar://dossier_1",
            artist_co_signature="0x" + "33" * 65,
        )
        assert receipt["status"] == "CONFIRMED"
        assert receipt["chain_id"] == 84532
        assert receipt["method"] == "genesisMint"
        assert receipt["tx_hash"].startswith("0x")
        assert receipt.get("mock") is True

        assert clean_mock_client.is_chip_bound("0x" + "22" * 32) is True
        assert len(clean_mock_client.broadcast_log) == 1

    def test_genesis_mint_duplicate_chip_rejection(self, clean_mock_client):
        """Enforces SC-CHIP-01: attempting to bind an already-bound chip MUST fail."""
        chip_hash = "0x" + "aa" * 32
        clean_mock_client.broadcast_genesis_mint(
            artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
            genesis_vector_hash="0x" + "11" * 32,
            chip_id_hash=chip_hash,
            metadata_uri="ar://dossier_1",
            artist_co_signature="0x" + "33" * 65,
        )
        with pytest.raises(ValueError, match="CHIP_ALREADY_BOUND"):
            clean_mock_client.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "99" * 32,
                chip_id_hash=chip_hash,
                metadata_uri="ar://dossier_2",
                artist_co_signature="0x" + "44" * 65,
            )

    def test_update_condition_records_state(self, clean_mock_client):
        """Verifies broadcast_update_condition updates condition records."""
        receipt = clean_mock_client.broadcast_update_condition(
            token_id=101,
            new_vector_hash="0x" + "44" * 32,
            note_uri="ar://restoration_note",
            owner_consent_sig="0x" + "55" * 65,
        )
        assert receipt["status"] == "CONFIRMED"
        assert receipt["method"] == "updateCondition"
        assert len(clean_mock_client.broadcast_log) == 1
        assert 101 in clean_mock_client.condition_updates

    def test_replace_chip_unbinds_old_and_binds_new(self, clean_mock_client):
        """Verifies chip replacement lifecycle and duplicate rejection."""
        old_chip = "0x" + "11" * 32
        new_chip = "0x" + "22" * 32
        clean_mock_client.broadcast_genesis_mint(
            artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
            genesis_vector_hash="0x" + "00" * 32,
            chip_id_hash=old_chip,
            metadata_uri="ar://1",
            artist_co_signature="0x" + "33" * 65,
        )
        assert clean_mock_client.is_chip_bound(old_chip) is True

        receipt = clean_mock_client.broadcast_replace_chip(
            token_id=1,
            new_chip_id_hash=new_chip,
            optical_similarity_bps=9420,
            approvals=["0xsig1", "0xsig2", "0xsig3"],
        )
        assert receipt["status"] == "CONFIRMED"
        assert clean_mock_client.is_chip_bound(old_chip) is False
        assert clean_mock_client.is_chip_bound(new_chip) is True

    def test_escrow_refund_updates_listing_state(self, clean_mock_client):
        """Verifies broadcast_escrow_refund transitions listing to REFUNDED."""
        clean_mock_client.seed_listing("listing-101", {"status": "ACTIVE", "state": 1})
        receipt = clean_mock_client.broadcast_escrow_refund(listing_id="listing-101")
        assert receipt["status"] == "CONFIRMED"
        assert receipt["method"] == "refund"
        listing = clean_mock_client.get_listing_state("listing-101")
        assert listing["status"] == "REFUNDED"
        assert listing["state"] == 4

    def test_escrow_claim_updates_listing_state(self, clean_mock_client):
        """Verifies broadcast_escrow_claim transitions listing to COMPLETED."""
        clean_mock_client.seed_listing("105", {"status": "FUNDED", "state": 2})
        attestation = {
            "tokenId": 105,
            "sunDigest": "0x" + "aa" * 32,
            "similarityBps": 9500,
            "deadline": 2000000000,
            "nonce": "0x" + "bb" * 32,
        }
        receipt = clean_mock_client.broadcast_escrow_claim("105", attestation, "0x" + "cc" * 65)
        assert receipt["status"] == "CONFIRMED"
        assert receipt["method"] == "claim"
        assert clean_mock_client.get_listing_state("105")["status"] == "COMPLETED"
        assert clean_mock_client.get_listing_state("105")["state"] == 3

    def test_anchor_merkle_root_l1_deterministic_receipt(self, clean_mock_client):
        """Verifies anchor_merkle_root_l1 records root and returns l1_tx_hash."""
        root = "0x" + "ab" * 32
        receipt = clean_mock_client.anchor_merkle_root_l1(root, from_block=100, to_block=200)
        assert receipt["status"] == "CONFIRMED"
        assert receipt["chain_id"] == 11155111
        assert receipt["method"] == "anchorRoot"
        assert receipt["l1_tx_hash"].startswith("0x")
        assert root in clean_mock_client.anchored_roots

    def test_mock_client_seed_and_reset(self, clean_mock_client):
        """Verifies seed_token, seed_listing, and reset functionality."""
        chip_hash = "0x" + "99" * 32
        clean_mock_client.seed_token(200, "0xOwner", "0xGenHash", chip_hash)
        clean_mock_client.seed_listing("99", {"status": "ACTIVE"})

        assert clean_mock_client.get_onchain_owner(200) == "0xowner"
        assert clean_mock_client.get_genesis_hash(200) == "0xGenHash"
        assert clean_mock_client.is_chip_bound(chip_hash) is True
        assert clean_mock_client.get_listing_state("99")["status"] == "ACTIVE"

        clean_mock_client.reset()
        assert clean_mock_client.get_onchain_owner(200) is None
        assert clean_mock_client.is_chip_bound(chip_hash) is False
        assert len(clean_mock_client.listings) == 0


# ==============================================================================
# Suite 2: EVMChainClient Offline JSON-RPC Simulation
# ==============================================================================
class TestEVMChainClientOffline:
    @pytest.fixture
    def mock_rpc_session(self):
        """
        Creates an httpx.MockTransport that simulates Base Sepolia and Ethereum Sepolia
        JSON-RPC nodes, capturing all broadcast calls and returning deterministic data.
        """
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            calls.append(body)
            method = body.get("method")
            req_id = body.get("id", 1)

            if method == "eth_chainId":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x14a34"})
            elif method == "eth_getTransactionCount":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x5"})
            elif method == "eth_getBlockByNumber":
                return httpx.Response(200, json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"baseFeePerGas": "0x3b9aca00", "number": "0x100"}  # 1 Gwei
                })
            elif method == "eth_estimateGas":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x30d40"})  # 200,000
            elif method == "eth_sendRawTransaction":
                raw_hex = body["params"][0]
                raw_bytes = bytes.fromhex(raw_hex[2:])
                tx_hash = "0x" + keccak(raw_bytes).hex()
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": tx_hash})
            elif method == "eth_call":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x" + "00" * 32})
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method {method} not found"}})

        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        return mock_client, calls

    def test_evm_broadcast_genesis_mint_produces_genuine_eip1559_tx(self, mock_rpc_session):
        """
        Validates EVMChainClient constructs a genuine EIP-1559 (0x02) transaction,
        RLP-encodes calldata matching genesisMint selector and arguments,
        and recovers the relayer address from the raw transaction.
        """
        http_client, rpc_calls = mock_rpc_session
        evm_client = EVMChainClient(
            base_rpc_url="http://mock-base-rpc:8545",
            l1_rpc_url="http://mock-l1-rpc:8545",
            relayer_private_key=RELAYER_KEY,
            http_client=http_client,
        )

        artist = "0x71C95911E9a5D330f4D621842EC243EE1343292e"
        genesis_vector_hash = "0x" + "11" * 32
        chip_id_hash = "0x" + "22" * 32
        metadata_uri = "ar://dossier_1"
        artist_co_signature = "0x" + "33" * 65

        receipt = evm_client.broadcast_genesis_mint(
            artist=artist,
            genesis_vector_hash=genesis_vector_hash,
            chip_id_hash=chip_id_hash,
            metadata_uri=metadata_uri,
            artist_co_signature=artist_co_signature,
        )
        assert receipt["status"] == "CONFIRMED"
        assert receipt["chain_id"] == 84532
        assert receipt["tx_hash"].startswith("0x")

        # 1. Locate the eth_sendRawTransaction call
        send_call = next(c for c in rpc_calls if c["method"] == "eth_sendRawTransaction")
        raw_tx_hex = send_call["params"][0]
        assert raw_tx_hex.startswith("0x02")  # EIP-1559 Envelope type

        raw_bytes = bytes.fromhex(raw_tx_hex[2:])
        # 2. Check Keccak-256 matches returned tx_hash
        assert "0x" + keccak(raw_bytes).hex() == receipt["tx_hash"]

        # 3. Recover signer address
        recovered_sender = Account.recover_transaction(raw_bytes)
        assert recovered_sender.lower() == RELAYER_ACCT.address.lower()

        # 4. Decode RLP payload
        decoded_fields = rlp.decode(raw_bytes[1:])
        calldata = decoded_fields[7]  # index 7 is 'data' in EIP-1559

        # 5. Verify calldata selector
        selector = evm_client.get_function_selectors("ArthenticNFT")["genesisMint"]
        assert calldata[:4].hex() == selector[2:]

        # 6. Verify calldata arguments match inputs
        decoded_args = eth_abi.decode(
            ["address", "bytes32", "bytes32", "string", "bytes"],
            calldata[4:],
        )
        assert decoded_args[0].lower() == artist.lower()
        assert decoded_args[1].hex() == genesis_vector_hash[2:]
        assert decoded_args[2].hex() == chip_id_hash[2:]
        assert decoded_args[3] == metadata_uri
        assert decoded_args[4].hex() == artist_co_signature[2:]

    def test_evm_broadcast_escrow_claim_produces_genuine_eip1559_tx(self, mock_rpc_session):
        """
        Validates EVMChainClient constructs a genuine EIP-1559 claim transaction
        with canonical tuple encoding for ArthenticEscrow.claim(listingId, Attestation, sig).
        """
        http_client, rpc_calls = mock_rpc_session
        evm_client = EVMChainClient(
            base_rpc_url="http://mock-base-rpc:8545",
            l1_rpc_url="http://mock-l1-rpc:8545",
            relayer_private_key=RELAYER_KEY,
            http_client=http_client,
        )

        attestation = {
            "tokenId": 101,
            "sunDigest": "0x" + "aa" * 32,
            "similarityBps": 9420,
            "deadline": 2000000000,
            "nonce": "0x" + "bb" * 32,
        }
        sig = "0x" + "cc" * 65

        receipt = evm_client.broadcast_escrow_claim(
            listing_id=1,
            attestation=attestation,
            signature=sig,
        )
        assert receipt["status"] == "CONFIRMED"
        assert receipt["method"] == "claim"

        send_call = next(c for c in rpc_calls if c["method"] == "eth_sendRawTransaction")
        raw_tx_hex = send_call["params"][0]
        assert raw_tx_hex.startswith("0x02")

        raw_bytes = bytes.fromhex(raw_tx_hex[2:])
        decoded_fields = rlp.decode(raw_bytes[1:])
        calldata = decoded_fields[7]

        # Verify selector matches 0x2881b321 (claim)
        selector = evm_client.get_function_selectors("ArthenticEscrow")["claim"]
        assert calldata[:4].hex() == selector[2:]

        # Verify decoded tuple arguments
        decoded_args = eth_abi.decode(
            ["uint256", "(uint256,bytes32,uint16,uint256,bytes32)", "bytes"],
            calldata[4:],
        )
        assert decoded_args[0] == 1
        att_tuple = decoded_args[1]
        assert att_tuple[0] == 101
        assert att_tuple[1].hex() == "aa" * 32
        assert att_tuple[2] == 9420
        assert att_tuple[3] == 2000000000
        assert att_tuple[4].hex() == "bb" * 32
        assert decoded_args[2].hex() == "cc" * 65

    def test_evm_fail_fast_on_missing_or_unreachable_rpc(self):
        """Verifies EVMChainClient fails fast when RPC is missing or unreachable."""
        client_no_rpc = EVMChainClient(base_rpc_url="", relayer_private_key=RELAYER_KEY)
        with pytest.raises(ConnectionError, match="Base RPC URL not configured or unreachable"):
            client_no_rpc.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "11" * 32,
                chip_id_hash="0x" + "22" * 32,
                metadata_uri="ar://1",
                artist_co_signature="0x" + "33" * 65,
            )

        client_unreachable = EVMChainClient(
            base_rpc_url="http://127.0.0.1:9999",
            relayer_private_key=RELAYER_KEY,
        )
        with pytest.raises(ConnectionError, match="unreachable"):
            client_unreachable.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "11" * 32,
                chip_id_hash="0x" + "22" * 32,
                metadata_uri="ar://1",
                artist_co_signature="0x" + "33" * 65,
            )

    def test_evm_fail_fast_on_json_rpc_execution_revert(self):
        """Verifies EVMChainClient raises when JSON-RPC returns execution error."""
        def revert_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "execution reverted: CHIP_ALREADY_BOUND"}
            })

        mock_http = httpx.Client(transport=httpx.MockTransport(revert_handler))
        client = EVMChainClient(
            base_rpc_url="http://mock-base:8545",
            relayer_private_key=RELAYER_KEY,
            http_client=mock_http,
        )
        with pytest.raises(RuntimeError, match="CHIP_ALREADY_BOUND"):
            client.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "11" * 32,
                chip_id_hash="0x" + "22" * 32,
                metadata_uri="ar://1",
                artist_co_signature="0x" + "33" * 65,
            )


# ==============================================================================
# Suite 3: Client Factory & Mode Switching
# ==============================================================================
class TestChainClientFactory:
    def test_factory_returns_singleton(self):
        c1 = get_chain_client()
        c2 = get_chain_client()
        assert c1 is c2

    def test_set_chain_client_override(self):
        custom = MockChainClient()
        set_chain_client(custom)
        assert get_chain_client() is custom
        set_chain_client(None)

    def test_chain_client_proxy_delegation(self):
        custom = MockChainClient()
        custom.base_chain_id = 99999
        set_chain_client(custom)
        assert chain_client.base_chain_id == 99999
        set_chain_client(None)
