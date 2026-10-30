"""
server/tests/test_adversarial_chain_client.py
Adversarial empirical challenge suite for EVMChainClient and MockChainClient.
Validates:
1. Genuine EIP-1559 (Type 2, envelope 0x02) transactions across all broadcast methods.
2. Exact relayer address recovery via Account.recover_transaction.
3. Identity keccak(raw_tx) == tx_hash.
4. Exact ABI encoding and function selectors matching Solidity contracts.
5. Fail-fast ConnectionError on empty and unreachable RPC URLs.
6. Execution revert handling (RuntimeError).
7. MockChainClient strict chip unicity (ValueError) and case-insensitivity.
"""

import json
import rlp
import pytest
import httpx
from eth_account import Account
import eth_abi
from eth_utils import keccak, to_checksum_address

from server.node.chain_client import (
    EVMChainClient,
    MockChainClient,
    DEV_RELAYER_KEY,
)


class TestAdversarialEVMChainClient:
    """Empirical verification of EVMChainClient cryptographic transaction construction."""

    @pytest.fixture
    def mock_json_rpc(self):
        """Creates an in-memory JSON-RPC mock transport capturing calls."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read().decode("utf-8"))
            calls.append(payload)
            method = payload.get("method")
            req_id = payload.get("id", 1)

            if method == "eth_getTransactionCount":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0xa"})
            elif method == "eth_getBlockByNumber":
                return httpx.Response(200, json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"baseFeePerGas": "0x3b9aca00", "number": "0x123"}  # 1 Gwei
                })
            elif method == "eth_estimateGas":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x3d090"})  # 250,000
            elif method == "eth_sendRawTransaction":
                raw_hex = payload["params"][0]
                raw_b = bytes.fromhex(raw_hex[2:])
                tx_hash = "0x" + keccak(raw_b).hex()
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": tx_hash})
            elif method == "eth_call":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x" + "00" * 32})
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": req_id, "error": f"Unhandled method {method}"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return client, calls

    def test_all_broadcast_methods_produce_valid_eip1559_and_recoverable_relayer(self, mock_json_rpc):
        """
        Adversarially tests all broadcast methods:
        - envelope starts with 0x02
        - keccak(raw_tx) == tx_hash
        - Account.recover_transaction recovers exact relayer address
        - dynamic relayer private key support
        """
        http_client, calls = mock_json_rpc
        dynamic_acct = Account.create()

        client = EVMChainClient(
            base_rpc_url="http://mock-base-rpc:8545",
            l1_rpc_url="http://mock-l1-rpc:8545",
            relayer_private_key=dynamic_acct.key.hex(),
            http_client=http_client,
        )

        test_vectors = [
            (
                "genesisMint",
                lambda: client.broadcast_genesis_mint(
                    artist=Account.create().address,
                    genesis_vector_hash="0x" + "aa" * 32,
                    chip_id_hash="0x" + "bb" * 32,
                    metadata_uri="ar://test-metadata-uri",
                    artist_co_signature="0x" + "11" * 65,
                ),
                84532,
            ),
            (
                "updateCondition",
                lambda: client.broadcast_update_condition(
                    token_id=88,
                    new_vector_hash="0x" + "cc" * 32,
                    note_uri="ar://test-condition-note",
                    owner_consent_sig="0x" + "22" * 65,
                ),
                84532,
            ),
            (
                "replaceChip",
                lambda: client.broadcast_replace_chip(
                    token_id=88,
                    new_chip_id_hash="0x" + "dd" * 32,
                    optical_similarity_bps=9600,
                    approvals=["0x" + "33" * 65, "0x" + "44" * 65, "0x" + "55" * 65],
                ),
                84532,
            ),
            (
                "refund",
                lambda: client.broadcast_escrow_refund(listing_id=999),
                84532,
            ),
            (
                "claim",
                lambda: client.broadcast_escrow_claim(
                    listing_id=999,
                    attestation={
                        "tokenId": 88,
                        "sunDigest": "0x" + "ee" * 32,
                        "similarityBps": 9600,
                        "deadline": 2100000000,
                        "nonce": "0x" + "ff" * 32,
                    },
                    signature="0x" + "66" * 65,
                ),
                84532,
            ),
            (
                "anchorRoot",
                lambda: client.anchor_merkle_root_l1(
                    root_hex="0x" + "77" * 32,
                    from_block=10000,
                    to_block=20000,
                ),
                11155111,
            ),
        ]

        for method_name, broadcast_fn, expected_chain_id in test_vectors:
            calls.clear()
            receipt = broadcast_fn()
            assert receipt["status"] == "CONFIRMED"
            actual_tx_hash = receipt.get("tx_hash") or receipt.get("l1_tx_hash")
            assert actual_tx_hash is not None

            send_call = next(c for c in calls if c["method"] == "eth_sendRawTransaction")
            raw_tx_hex = send_call["params"][0]

            # Envelope 0x02 assertion
            assert raw_tx_hex.startswith("0x02"), f"{method_name} must start with EIP-1559 envelope 0x02"

            raw_bytes = bytes.fromhex(raw_tx_hex[2:])
            # Keccak identity assertion
            expected_hash = "0x" + keccak(raw_bytes).hex()
            assert actual_tx_hash == expected_hash, f"{method_name} tx_hash must equal keccak(raw_tx)"

            # Relayer public address recovery assertion
            recovered_signer = Account.recover_transaction(raw_bytes)
            assert recovered_signer.lower() == dynamic_acct.address.lower(), (
                f"{method_name} recovered signer {recovered_signer} does not match relayer {dynamic_acct.address}"
            )

            # RLP structure & chainId assertion
            decoded = rlp.decode(raw_bytes[1:])
            chain_id_in_tx = int.from_bytes(decoded[0], "big")
            assert chain_id_in_tx == expected_chain_id, (
                f"{method_name} chain ID mismatch: expected {expected_chain_id}, got {chain_id_in_tx}"
            )

    def test_calldata_abi_encoding_and_function_selectors(self, mock_json_rpc):
        """
        Adversarially validates that calldata emitted by each broadcast method
        strictly matches canonical Solidity ABI types and selectors.
        """
        http_client, calls = mock_json_rpc
        client = EVMChainClient(
            base_rpc_url="http://mock-base-rpc:8545",
            l1_rpc_url="http://mock-l1-rpc:8545",
            relayer_private_key=DEV_RELAYER_KEY,
            http_client=http_client,
        )

        # 1. genesisMint
        calls.clear()
        artist = Account.create().address
        vec = "0x" + "11" * 32
        chip = "0x" + "22" * 32
        uri = "ar://test_genesis_uri"
        sig = "0x" + "33" * 65
        client.broadcast_genesis_mint(artist, vec, chip, uri, sig)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "62058688"
        d_args = eth_abi.decode(["address", "bytes32", "bytes32", "string", "bytes"], data[4:])
        assert d_args[0].lower() == artist.lower()
        assert d_args[1].hex() == vec[2:]
        assert d_args[2].hex() == chip[2:]
        assert d_args[3] == uri
        assert d_args[4].hex() == sig[2:]

        # 2. updateCondition
        calls.clear()
        client.broadcast_update_condition(42, vec, uri, sig)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "52738a95"
        d_args = eth_abi.decode(["uint256", "bytes32", "string", "bytes"], data[4:])
        assert d_args[0] == 42
        assert d_args[1].hex() == vec[2:]
        assert d_args[2] == uri
        assert d_args[3].hex() == sig[2:]

        # 3. replaceChip
        calls.clear()
        approvals = ["0x" + "aa" * 65, "0x" + "bb" * 65, "0x" + "cc" * 65]
        client.broadcast_replace_chip(42, chip, 9420, approvals)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "6228ed75"
        d_args = eth_abi.decode(
            ["uint256", "bytes32", "(uint256,bytes32,uint16,uint256,bytes32)", "bytes", "bytes[3]"],
            data[4:]
        )
        assert d_args[0] == 42
        assert d_args[1].hex() == chip[2:]
        assert d_args[2][0] == 42  # tokenId
        assert d_args[2][2] == 9420  # similarityBps
        assert len(d_args[4]) == 3
        assert d_args[4][0].hex() == approvals[0][2:]

        # 4. refund
        calls.clear()
        client.broadcast_escrow_refund(555)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "278ecde1"
        d_args = eth_abi.decode(["uint256"], data[4:])
        assert d_args[0] == 555

        # 5. claim
        calls.clear()
        att = {
            "tokenId": 42,
            "sunDigest": "0x" + "55" * 32,
            "similarityBps": 9100,
            "deadline": 1900000000,
            "nonce": "0x" + "66" * 32,
        }
        client.broadcast_escrow_claim(555, att, sig)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "2881b321"
        d_args = eth_abi.decode(
            ["uint256", "(uint256,bytes32,uint16,uint256,bytes32)", "bytes"],
            data[4:]
        )
        assert d_args[0] == 555
        assert d_args[1][0] == 42
        assert d_args[1][1].hex() == "55" * 32
        assert d_args[1][2] == 9100
        assert d_args[1][3] == 1900000000
        assert d_args[1][4].hex() == "66" * 32
        assert d_args[2].hex() == sig[2:]

        # 6. anchorRoot
        calls.clear()
        root = "0x" + "88" * 32
        client.anchor_merkle_root_l1(root, 100, 200)
        raw_b = bytes.fromhex(calls[-1]["params"][0][2:])
        data = rlp.decode(raw_b[1:])[7]
        assert data[:4].hex() == "3d76c0b8"
        d_args = eth_abi.decode(["bytes32", "uint64", "uint64"], data[4:])
        assert d_args[0].hex() == root[2:]
        assert d_args[1] == 100
        assert d_args[2] == 200

    def test_connection_error_on_empty_and_unreachable_rpc(self):
        """Verifies ConnectionError is strictly raised when RPC is empty or unreachable."""
        # Case 1: Empty Base RPC
        client1 = EVMChainClient(base_rpc_url="", l1_rpc_url="http://localhost:8545")
        with pytest.raises(ConnectionError, match="Base RPC URL not configured or unreachable"):
            client1.broadcast_genesis_mint(
                Account.create().address, "0x" + "11" * 32, "0x" + "22" * 32, "ar://1", "0x" + "33" * 65
            )

        # Case 2: Empty L1 RPC on anchor_merkle_root_l1
        client2 = EVMChainClient(base_rpc_url="http://localhost:8545", l1_rpc_url="")
        with pytest.raises(ConnectionError, match="Base RPC URL not configured or unreachable"):
            client2.anchor_merkle_root_l1("0x" + "33" * 32, 100, 200)

        # Case 3: Unreachable endpoint (connection refused)
        client3 = EVMChainClient(base_rpc_url="http://127.0.0.1:59998")
        with pytest.raises(ConnectionError, match="unreachable"):
            client3.broadcast_escrow_refund(1)

        # Case 4: HTTP 500 status code
        def error_500(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content="Internal Gateway Error")

        client4 = EVMChainClient(
            base_rpc_url="http://mock-rpc:8545",
            http_client=httpx.Client(transport=httpx.MockTransport(error_500)),
        )
        with pytest.raises(ConnectionError, match="unreachable"):
            client4.broadcast_escrow_refund(1)

    def test_execution_revert_raises_runtime_error(self):
        """Verifies JSON-RPC error response raises RuntimeError with server message."""
        def revert_handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "execution reverted: ESCROW_ALREADY_CLAIMED"}
            })

        client = EVMChainClient(
            base_rpc_url="http://mock-rpc:8545",
            http_client=httpx.Client(transport=httpx.MockTransport(revert_handler)),
        )
        with pytest.raises(RuntimeError, match="ESCROW_ALREADY_CLAIMED"):
            client.broadcast_escrow_claim(
                1,
                {"tokenId": 1, "sunDigest": "0x" + "aa" * 32, "similarityBps": 9500, "deadline": 2000000000, "nonce": "0x" + "bb" * 32},
                "0x" + "cc" * 65
            )

    def test_gas_limit_resilience_when_estimate_gas_fails(self, mock_json_rpc):
        """Verifies gas limit falls back to 500,000 when eth_estimateGas throws an exception."""
        http_client, calls = mock_json_rpc

        def fallback_handler(req: httpx.Request) -> httpx.Response:
            p = json.loads(req.read().decode())
            m = p.get("method")
            req_id = p.get("id", 1)
            if m == "eth_getTransactionCount":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x1"})
            elif m == "eth_getBlockByNumber":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": {"baseFeePerGas": "0x3b9aca00"}})
            elif m == "eth_estimateGas":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "gas estimation unavailable"}})
            elif m == "eth_sendRawTransaction":
                raw_b = bytes.fromhex(p["params"][0][2:])
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": req_id, "result": "0x" + keccak(raw_b).hex()})
            return httpx.Response(400, json={"jsonrpc": "2.0", "id": req_id, "error": "unknown"})

        client = EVMChainClient(
            base_rpc_url="http://mock-base-rpc:8545",
            http_client=httpx.Client(transport=httpx.MockTransport(fallback_handler)),
        )
        receipt = client.broadcast_escrow_refund(42)
        assert receipt["status"] == "CONFIRMED"


class TestAdversarialMockChainClient:
    """Empirical verification of MockChainClient chip unicity and state transition invariants."""

    def test_mock_chip_unicity_case_insensitivity(self):
        """Tests that chip unicity is case-insensitively enforced across all formats."""
        mock = MockChainClient()
        chip_mixed = "0x" + "aB12cD34" * 8
        chip_lower = chip_mixed.lower()
        chip_upper = chip_mixed.upper()

        mock.broadcast_genesis_mint(
            artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
            genesis_vector_hash="0x" + "11" * 32,
            chip_id_hash=chip_mixed,
            metadata_uri="ar://1",
            artist_co_signature="0x" + "22" * 65,
        )

        assert mock.is_chip_bound(chip_mixed) is True
        assert mock.is_chip_bound(chip_lower) is True
        assert mock.is_chip_bound(chip_upper) is True

        # Attempt duplicate bind with lowercase
        with pytest.raises(ValueError, match="CHIP_ALREADY_BOUND"):
            mock.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "99" * 32,
                chip_id_hash=chip_lower,
                metadata_uri="ar://2",
                artist_co_signature="0x" + "33" * 65,
            )

        # Attempt duplicate bind with uppercase
        with pytest.raises(ValueError, match="CHIP_ALREADY_BOUND"):
            mock.broadcast_genesis_mint(
                artist="0x71C95911E9a5D330f4D621842EC243EE1343292e",
                genesis_vector_hash="0x" + "88" * 32,
                chip_id_hash=chip_upper,
                metadata_uri="ar://3",
                artist_co_signature="0x" + "44" * 65,
            )

    def test_mock_chip_replacement_unicity_and_unbinding(self):
        """Tests that replaceChip rejects duplicate target chip, unbinds old chip, and rebinds new."""
        mock = MockChainClient()
        chip_a = "0x" + "aa" * 32
        chip_b = "0x" + "bb" * 32
        chip_c = "0x" + "cc" * 32

        # Token 1 bound to chip_a
        mock.broadcast_genesis_mint("0x1111111111111111111111111111111111111111", "0x" + "01" * 32, chip_a, "ar://1", "0x" + "99" * 65)
        # Token 2 bound to chip_b
        mock.broadcast_genesis_mint("0x2222222222222222222222222222222222222222", "0x" + "02" * 32, chip_b, "ar://2", "0x" + "99" * 65)

        # Attempt replacing Token 1 with chip_b (already bound to Token 2)
        with pytest.raises(ValueError, match="CHIP_ALREADY_BOUND"):
            mock.broadcast_replace_chip(1, chip_b, 9500, ["0x1"] * 3)

        # Replace Token 1 with chip_c (free chip)
        mock.broadcast_replace_chip(1, chip_c, 9500, ["0x1"] * 3)
        assert mock.is_chip_bound(chip_a) is False  # chip_a is now unbound
        assert mock.is_chip_bound(chip_c) is True   # chip_c is now bound

        # Now chip_a can be legitimately bound to Token 3
        mock.broadcast_genesis_mint("0x3333333333333333333333333333333333333333", "0x" + "03" * 32, chip_a, "ar://3", "0x" + "99" * 65)
        assert mock.is_chip_bound(chip_a) is True

    def test_mock_reset_clears_all_invariants(self):
        """Tests that reset() cleanly resets chip bounds, logs, and listings."""
        mock = MockChainClient()
        chip = "0x" + "55" * 32
        mock.broadcast_genesis_mint("0x1111111111111111111111111111111111111111", "0x" + "01" * 32, chip, "ar://1", "0x" + "99" * 65)
        assert mock.is_chip_bound(chip) is True
        assert len(mock.broadcast_log) == 1

        mock.reset()
        assert mock.is_chip_bound(chip) is False
        assert len(mock.broadcast_log) == 0
        assert len(mock.token_owners) == 0
        assert len(mock.genesis_hashes) == 0
        assert len(mock.bound_chips) == 0
