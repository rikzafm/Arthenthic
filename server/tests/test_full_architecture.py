import pytest
from fastapi.testclient import TestClient
from server.main import app
from server.db.redis_hotpath import redis_hotpath
from server.indexer.event_listener import indexer_listener
from server.indexer.merkle_batcher import merkle_worker
from server.paymaster.policy_engine import paymaster_engine
from server.paymaster.balance_monitor import balance_monitor

client = TestClient(app)

def test_redis_hotpath_6_keys():
    # 1. sun:ctr monotonic check
    ok, err = redis_hotpath.check_and_update_sun_counter("04TEST1234", 10)
    assert ok is True
    ok, err = redis_hotpath.check_and_update_sun_counter("04TEST1234", 10)
    assert ok is False # Replay rejected!
    ok, err = redis_hotpath.check_and_update_sun_counter("04TEST1234", 11)
    assert ok is True # Monotonic increment allowed

    # 2. nonce anti-replay
    ok = redis_hotpath.set_attestation_nonce("0xnonce1")
    assert ok is True
    ok = redis_hotpath.set_attestation_nonce("0xnonce1")
    assert ok is False # Duplicate rejected!

    # 3. quota atomic counter
    allowed, used, max_q = redis_hotpath.check_and_increment_quota("0xwallet", "T1", "2026-10", 2)
    assert allowed is True and used == 1
    allowed, used, max_q = redis_hotpath.check_and_increment_quota("0xwallet", "T1", "2026-10", 2)
    assert allowed is True and used == 2
    allowed, used, max_q = redis_hotpath.check_and_increment_quota("0xwallet", "T1", "2026-10", 2)
    assert allowed is False # Limit exceeded!

    # 4. rate limiting
    allowed, count = redis_hotpath.check_rate_limit("192.168.1.1", max_requests=2)
    assert allowed is True and count == 1
    allowed, count = redis_hotpath.check_rate_limit("192.168.1.1", max_requests=2)
    assert allowed is True and count == 2
    allowed, count = redis_hotpath.check_rate_limit("192.168.1.1", max_requests=2)
    assert allowed is False # Rate limit hit!

    # 5. pm:balance
    balance_monitor.update_balance(2000000000000000000) # 2 ETH
    b = redis_hotpath.get_paymaster_balance(84532)
    assert b["status"] == "ok"

    # 6. idx:head
    redis_hotpath.update_indexer_head(84532, 10050, "0xhash50")
    head = redis_hotpath.get_indexer_head(84532)
    assert head["block_number"] == 10050

def test_paymaster_policy_engine_sponsorship_and_fallback():
    # T1 Sponsorship
    res = paymaster_engine.evaluate_sponsorship("0xcollector99", "claim", ["Collector"])
    assert res["sponsored"] is True
    assert res["tier"] == "T1"

    # Non-sponsored method fallback
    res = paymaster_engine.evaluate_sponsorship("0xcollector99", "unknownMethod", ["Collector"])
    assert res["sponsored"] is False
    assert res["fallback"] == "SELF_PAY_L2"

def test_public_guest_nfc_verification():
    from server.crypto.sun import sun_verifier
    params = sun_verifier.generate_sun_params("04A1B2C3D4E580")
    res = client.post("/v1/verify/public", json={
        "uid": params["uid"],
        "ctr": params["ctr"],
        "cmac": params["cmac"],
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "VALID"
    assert data["statusBadge"] == "CLEAR"
    assert "coaUrl" in data

def test_certificate_of_authenticity_endpoint():
    res = client.get("/v1/genesis/coa/101")
    assert res.status_code == 200
    data = res.json()
    assert data["tokenId"] == "101"
    assert data["cryptographicHashVerified"] is True
    assert data["l1MerkleAnchored"] is True
    assert data["statusBadge"] == "CLEAR"

def test_marketplace_c12_ownership_sync_check():
    # Seed listings first
    client.get("/v1/marketplace/listings")
    listings_res = client.get("/v1/marketplace/listings")
    listings = listings_res.json()["listings"]
    assert len(listings) > 0
    first_id = listings[0]["id"]

    res = client.get(f"/v1/marketplace/listings/{first_id}/verify-sync")
    assert res.status_code == 200
    data = res.json()
    assert data["feature_code"] == "C-12"
    assert data["synchronized"] is True
    assert data["statusBadge"] == "CLEAR"

def test_restoration_lifecycle_and_chip_replacement():
    # E-01: Collector creates restoration request
    req_res = client.post("/v1/conservation/requests", json={
        "token_id": 101,
        "conservator_wallet": "0xConservatorStudio000000000000000000001",
        "damage_description": "Micro craquelure near bottom left corner",
    })
    assert req_res.status_code == 200
    req_id = req_res.json()["request"]["id"]

    # F-05: Propose 3-of-3 chip replacement
    chip_res = client.post("/v1/conservation/chips/replace/propose", json={
        "token_id": 101,
        "old_chip_id_hash": "0xoldchip123",
        "new_chip_id_hash": "0xnewchip456",
        "optical_similarity_bps": 9400,
        "collector_wallet": "0xcollector",
        "artist_wallet": "0xartist",
        "verifier_wallet": "0xverifier",
    })
    assert chip_res.status_code == 200
    rep_id = chip_res.json()["replacement_id"]

    # Sign 1/3 (Collector)
    s1 = client.post(f"/v1/conservation/chips/replace/{rep_id}/sign", json={
        "party": "collector",
        "signature": "0xsig_collector_1",
    })
    assert s1.status_code == 200
    assert s1.json()["collected_signatures"] == "1/3"

    # Sign 2/3 (Artist)
    s2 = client.post(f"/v1/conservation/chips/replace/{rep_id}/sign", json={
        "party": "artist",
        "signature": "0xsig_artist_2",
    })
    assert s2.status_code == 200
    assert s2.json()["collected_signatures"] == "2/3"

    # Sign 3/3 (Verifier) -> Execution Ready!
    s3 = client.post(f"/v1/conservation/chips/replace/{rep_id}/sign", json={
        "party": "verifier",
        "signature": "0xsig_verifier_3",
    })
    assert s3.status_code == 200
    assert s3.json()["collected_signatures"] == "3/3"
    assert s3.json()["status"] == "READY_FOR_EXECUTION"

def test_indexer_reorg_and_merkle_batching():
    # Reorg safe block ingestion
    res = indexer_listener.process_incoming_block(
        block_number=1001,
        block_hash="0xblock1001",
        parent_hash="0xblock1000",
        logs=[{
            "event_type": "GENESIS_MINTED",
            "token_id": 101,
            "actor": "0xartist",
            "role": "Artist",
            "details": "Minted on Base L2",
        }]
    )
    assert res["success"] is True

    # Merkle Batch Worker
    tree_root, tree = merkle_worker.build_merkle_tree(["leaf1", "leaf2", "leaf3", "leaf4"])
    assert tree_root.startswith("0x")
    assert len(tree_root) == 66
    proof = merkle_worker.get_inclusion_proof(tree, "leaf1")
    assert len(proof) > 0


def test_evm_chain_client_and_escrow_sweep():
    from server.node.chain_client import chain_client

    nft_abi = chain_client.get_abi("ArthenticNFT")
    escrow_abi = chain_client.get_abi("ArthenticEscrow")
    anchor_abi = chain_client.get_abi("MerkleAnchor")
    assert len(nft_abi) > 0
    assert len(escrow_abi) > 0
    assert len(anchor_abi) > 0

    selectors = chain_client.get_function_selectors("ArthenticEscrow")
    assert "claim" in selectors
    assert "createListing" in selectors

    l1_receipt = chain_client.anchor_merkle_root_l1(
        "0x" + "ab" * 32, from_block=100, to_block=200
    )
    assert l1_receipt["status"] == "CONFIRMED"
    assert l1_receipt["l1_tx_hash"].startswith("0x")

    sweep_res = client.post("/v1/marketplace/escrow/sweep-expired")
    assert sweep_res.status_code == 200
    assert sweep_res.json()["feature_code"] == "C-12-AUTO-REFUND"

