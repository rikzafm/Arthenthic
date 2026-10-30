import time
import secrets
from typing import Optional
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient

from server.main import app
from server.node.hsm_signer import TEST_SIGNER_PRIVATE_KEY

client = TestClient(app)


def make_test_escrow_attestation(
    token_id: int = 101,
    sun_digest: str = "0x" + "11" * 32,
    similarity_bps: int = 9420,
    validity_seconds: int = 300,
    private_key: str = TEST_SIGNER_PRIVATE_KEY,
    escrow_address: str = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    chain_id: int = 84532,
    nonce: Optional[str] = None,
):
    acct = Account.from_key(private_key)
    deadline = int(time.time()) + validity_seconds
    if not nonce:
        nonce = "0x" + secrets.token_hex(32)

    domain = {
        "name": "ArthenticEscrow",
        "version": "1",
        "chainId": chain_id,
        "verifyingContract": escrow_address,
    }
    types = {
        "Attestation": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "sunDigest", "type": "bytes32"},
            {"name": "similarityBps", "type": "uint16"},
            {"name": "deadline", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]
    }
    msg = {
        "tokenId": token_id,
        "sunDigest": sun_digest,
        "similarityBps": similarity_bps,
        "deadline": deadline,
        "nonce": nonce,
    }
    signable = encode_typed_data(domain_data=domain, message_types=types, message_data=msg)
    signed = acct.sign_message(signable)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex

    return {
        "attestation": {
            "tokenId": token_id,
            "sunDigest": sun_digest,
            "similarityBps": similarity_bps,
            "deadline": deadline,
            "nonce": nonce,
        },
        "attestation_signature": sig_hex,
    }


def test_marketplace_seed_and_3way_split():
    """Verifies A4 Dual Asset (USDC + ETH) seeding and A5 3-Way Split (93.5% / 5.0% / 1.5%)."""
    res = client.get("/v1/marketplace/listings")
    assert res.status_code == 200
    data = res.json()
    assert "architecture_policies" in data
    listings = data["listings"]
    assert len(listings) >= 3

    usdc_listing = next(l for l in listings if l["asset"] == "USDC")
    split = usdc_listing["split_breakdown"]
    assert split["seller_pct"] == 93.5
    assert split["artist_pct"] == 5.0
    assert split["platform_pct"] == 1.5
    assert abs(
        split["seller_payout_amount"] + split["artist_royalty_amount"] + split["platform_fee_amount"]
        - usdc_listing["price_amount"]
    ) < 0.01


def test_create_listing_and_usdc_permit2_escrow_lifecycle():
    """
    Tests full UC-C lifecycle:
    1. C-01 Create Listing (Hybrid Meta-Tx gasless intent)
    2. C-04 Deposit USDC into Escrow (Permit2 signature + 3-way lock)
    3. A6 Hardware Gate check (blocks C-06 release if has_pro_lidar=False)
    4. C-06 Confirm Physical Delivery with Pro LiDAR + L1 NFC -> Atomic 3-Way Release
    """
    # 1. Create a 10,000 USDC listing
    create_res = client.post(
        "/v1/marketplace/listings",
        json={
            "token_id": 101,
            "artwork_title": "Composition in Ultramarine #9",
            "artist_name": "Studio Arthentic",
            "artist_wallet": "0xArtistStudioArthentic0000000000000000001",
            "seller_wallet": "0xSellerCollector0000000000000000000000101",
            "price_amount": 10000.0,
            "asset": "USDC",
            "signature": "0xmeta_tx_c01_test_sig",
        },
    )
    assert create_res.status_code == 200
    listing = create_res.json()["listing"]
    listing_id = listing["id"]
    assert listing["status"] == "ACTIVE"

    # 2. Deposit 10,000 USDC into Escrow via MetaMask + Permit2
    dep_res = client.post(
        f"/v1/marketplace/listings/{listing_id}/deposit",
        json={
            "buyer_wallet": "0xBuyerMetaMask000000000000000000000000101",
            "wallet_provider": "metamask",
            "permit2_signature": "0xpermit2_eip2612_usdc_sig",
            "tx_signature": "0xmetamask_deposit_tx_sig",
        },
    )
    assert dep_res.status_code == 200
    escrow = dep_res.json()["escrow"]
    escrow_id = escrow["id"]
    assert escrow["status"] == "LOCKED"
    assert escrow["seller_payout_amount"] == 9350.0
    assert escrow["artist_royalty_amount"] == 500.0
    assert escrow["platform_fee_amount"] == 150.0

    # 3. Attempt C-06 Delivery Confirmation from a non-Pro phone without LiDAR (A6 Gate)
    no_lidar_res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": "0xBuyerMetaMask000000000000000000000000101",
            "l1_nfc_verified": True,
            "has_pro_lidar": False,
            "l2_similarity_score": 0.95,
        },
    )
    assert no_lidar_res.status_code == 403
    assert "A6 Hardware Tier Gate" in no_lidar_res.json()["detail"]

    # 4. Confirm Delivery with iPhone Pro LiDAR + Genuine EIP-712 Protocol Node Attestation
    att_payload = make_test_escrow_attestation(token_id=101, similarity_bps=9420)
    rel_res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": "0xBuyerMetaMask000000000000000000000000101",
            "l1_nfc_verified": True,
            "has_pro_lidar": True,
            "l2_similarity_score": 0.942,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert rel_res.status_code == 200
    released = rel_res.json()["escrow"]
    assert released["status"] == "DELIVERY_VERIFIED_RELEASED"
    assert released["release_tx_hash"].startswith("0x")


def test_escrow_dispute_and_arbitrator_refund():
    """Tests C-10 Dispute when L2 surface scan fails (< 0.85) and C-11 Arbitrator refund."""
    create_res = client.post(
        "/v1/marketplace/listings",
        json={
            "token_id": 102,
            "artwork_title": "Bronze Study IV",
            "artist_name": "Elena Rostova",
            "seller_wallet": "0xSeller0000000000000000000000000000000102",
            "price_amount": 2.5,
            "asset": "ETH",
        },
    )
    listing_id = create_res.json()["listing"]["id"]

    dep_res = client.post(
        f"/v1/marketplace/listings/{listing_id}/deposit",
        json={
            "buyer_wallet": "0xBuyer00000000000000000000000000000000102",
            "wallet_provider": "smart_wallet",
        },
    )
    escrow_id = dep_res.json()["escrow"]["id"]

    # C-10 Open Dispute due to surface mismatch (0.62 < 0.85)
    disp_res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/dispute",
        json={
            "caller_wallet": "0xBuyer00000000000000000000000000000000102",
            "reason": "L2 LiDAR surface similarity dropped to 62% on top-right corner.",
            "l2_similarity_score": 0.62,
        },
    )
    assert disp_res.status_code == 200
    assert disp_res.json()["escrow"]["status"] == "DISPUTED"

    # C-11 Arbitrator resolves in favor of Buyer refund
    res_res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/resolve",
        json={
            "action": "refund_buyer",
            "resolution_note": "Confirmed surface discrepancy; full ETH refunded to buyer.",
        },
    )
    assert res_res.status_code == 200
    assert res_res.json()["escrow"]["status"] == "REFUNDED_TO_BUYER"


def test_base_l2_dex_swapping_and_swap_and_deposit():
    """
    Tests:
    1. DEX quote: ETH -> USDC (1 ETH = 3,000 USDC)
    2. DEX quote: USDC -> ETH (3,000 USDC = 1.0 ETH)
    3. Direct swap execution
    4. 1-Step Swap & Deposit: Buyer brings ETH, swaps to USDC on Aerodrome DEX, and deposits into escrow.
    """
    # 1. Quote ETH -> USDC
    quote_eth = client.get("/v1/marketplace/swap/quote?from_asset=ETH&to_asset=USDC&amount=2.5").json()
    assert quote_eth["out_amount"] == 7500.0
    assert quote_eth["execution_rate"] == 3000.0
    assert quote_eth["minimum_received"] == 7462.5  # 0.5% slippage

    # 2. Quote USDC -> ETH
    quote_usdc = client.get("/v1/marketplace/swap/quote?from_asset=USDC&to_asset=ETH&amount=6000.0").json()
    assert quote_usdc["out_amount"] == 2.0

    # 3. Swap execution
    swap_res = client.post(
        "/v1/marketplace/swap/execute",
        json={
            "caller_wallet": "0xSwapper00000000000000000000000000000000001",
            "from_asset": "ETH",
            "to_asset": "USDC",
            "in_amount": 1.0,
            "min_out_amount": 2980.0,
            "slippage_bps": 50,
        },
    )
    assert swap_res.status_code == 200
    swap_data = swap_res.json()
    assert swap_data["success"] is True
    assert swap_data["tx_hash"].startswith("0x")
    assert "Aerodrome" in swap_data["quote"]["route"]

    # 4. 1-Step Swap and Deposit: Listing costs 12,500 USDC; buyer brings 4.2 ETH
    # First create listing
    lst_res = client.post(
        "/v1/marketplace/listings",
        json={
            "token_id": 105,
            "artwork_title": "Grand Gallery Study in Indigo",
            "artist_name": "Studio Arthentic",
            "seller_wallet": "0xGallerySeller0000000000000000000000000001",
            "price_amount": 12500.0,
            "asset": "USDC",
            "image_url": "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119",
            "medium": "Oil & dammar resin on linen",
            "dimensions": "140 x 100 cm",
            "year": 2024,
        },
    ).json()
    listing_id = lst_res["listing"]["id"]

    # Buyer has 4.2 ETH (4.2 * 3000 = 12,600 USDC, which covers 12,500 USDC)
    swap_dep_res = client.post(
        f"/v1/marketplace/listings/{listing_id}/swap-and-deposit",
        json={
            "buyer_wallet": "0xBuyerWithEth000000000000000000000000000001",
            "from_asset": "ETH",
            "in_amount": 4.2,
            "wallet_provider": "metamask",
        },
    )
    assert swap_dep_res.status_code == 200
    sd_data = swap_dep_res.json()
    assert sd_data["success"] is True
    assert sd_data["escrow"]["status"] == "LOCKED"
    assert sd_data["swap_details"]["spent"] == "4.2 ETH"
    assert "12600.0 USDC" in sd_data["swap_details"]["converted_to"]


def test_upload_listing_image():
    """Tests multipart upload of painting photo taken via camera."""
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
    res = client.post(
        "/v1/marketplace/listings/upload-image",
        files={"file": ("canvas_test.jpg", fake_jpeg, "image/jpeg")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["image_url"].startswith("/static/uploads/canvas_")
    assert data["file_size_bytes"] == len(fake_jpeg)


# ==============================================================================
# Milestone 3: Escrow Attestation Security & Edge-Case Negative Tests
# ==============================================================================

def _create_test_locked_escrow(token_id: int = 201) -> tuple:
    """Helper to create a listing and deposit into escrow, returning (escrow_id, buyer_wallet)."""
    buyer_wallet = f"0xBuyerMetaMask000000000000000000000000{token_id}"
    create_res = client.post(
        "/v1/marketplace/listings",
        json={
            "token_id": token_id,
            "artwork_title": f"Test Security Canvas #{token_id}",
            "artist_name": "Test Artist",
            "artist_wallet": "0xArtist00000000000000000000000000000000001",
            "seller_wallet": "0xSeller00000000000000000000000000000000001",
            "price_amount": 5000.0,
            "asset": "USDC",
        },
    )
    assert create_res.status_code == 200
    listing_id = create_res.json()["listing"]["id"]

    dep_res = client.post(
        f"/v1/marketplace/listings/{listing_id}/deposit",
        json={
            "buyer_wallet": buyer_wallet,
            "wallet_provider": "metamask",
        },
    )
    assert dep_res.status_code == 200
    escrow_id = dep_res.json()["escrow"]["id"]
    return escrow_id, buyer_wallet


def test_confirm_delivery_rejects_raw_booleans():
    """Security test: rejects delivery confirmation when EIP-712 attestation is missing."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=301)
    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "l1_nfc_verified": True,
            "has_pro_lidar": True,
            "l2_similarity_score": 0.942,
        },
    )
    assert res.status_code == 400
    assert "Missing required EIP-712 Protocol Node attestation" in res.json()["detail"]


def test_confirm_delivery_invalid_node_signature():
    """Security test: rejects attestation signed by unauthorized/rogue private key."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=302)
    rogue_key = Account.create().key.hex()
    att_payload = make_test_escrow_attestation(token_id=302, private_key=rogue_key)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "Invalid protocol node attestation signature" in res.json()["detail"]


def test_confirm_delivery_expired_deadline():
    """Security test: rejects attestation whose deadline has expired."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=303)
    att_payload = make_test_escrow_attestation(token_id=303, validity_seconds=-60)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Attestation deadline expired" in res.json()["detail"]


def test_confirm_delivery_replayed_nonce():
    """Security test: anti-replay enforcement rejects re-using a consumed nonce."""
    escrow_id_1, buyer_wallet_1 = _create_test_locked_escrow(token_id=304)
    escrow_id_2, buyer_wallet_2 = _create_test_locked_escrow(token_id=305)

    fixed_nonce = "0x" + secrets.token_hex(32)

    # First use on escrow 1 -> succeeds
    att_payload_1 = make_test_escrow_attestation(token_id=304, nonce=fixed_nonce)
    res_1 = client.post(
        f"/v1/marketplace/escrows/{escrow_id_1}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet_1,
            "attestation": att_payload_1["attestation"],
            "attestation_signature": att_payload_1["attestation_signature"],
        },
    )
    assert res_1.status_code == 200

    # Second use on escrow 2 with same nonce -> fails with anti-replay error
    att_payload_2 = make_test_escrow_attestation(token_id=305, nonce=fixed_nonce)
    res_2 = client.post(
        f"/v1/marketplace/escrows/{escrow_id_2}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet_2,
            "attestation": att_payload_2["attestation"],
            "attestation_signature": att_payload_2["attestation_signature"],
        },
    )
    assert res_2.status_code == 400
    assert "Anti-replay violation: Nonce" in res_2.json()["detail"]


def test_confirm_delivery_similarity_below_threshold():
    """Security test: rejects attestation with similarity below 8500 bps (85.0%)."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=306)
    att_payload = make_test_escrow_attestation(token_id=306, similarity_bps=8000)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "L2 Surface Similarity" in res.json()["detail"]
    assert "below threshold" in res.json()["detail"]


def test_confirm_delivery_missing_l1_nfc():
    """Security test: rejects delivery confirmation when l1_nfc_verified is explicitly False."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=307)
    att_payload = make_test_escrow_attestation(token_id=307)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "l1_nfc_verified": False,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Invariant #3 Violation" in res.json()["detail"]


def test_confirm_delivery_missing_lidar():
    """Security test: rejects delivery confirmation when has_pro_lidar is explicitly False (A6 Gate)."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=308)
    att_payload = make_test_escrow_attestation(token_id=308)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "has_pro_lidar": False,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "A6 Hardware Tier Gate" in res.json()["detail"]


def test_confirm_delivery_token_id_mismatch():
    """Security test: rejects attestation whose tokenId does not match escrow tokenId."""
    escrow_id, buyer_wallet = _create_test_locked_escrow(token_id=309)
    # Generate attestation for token 999 instead of 309
    att_payload = make_test_escrow_attestation(token_id=999)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": buyer_wallet,
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 400
    assert "Attestation token ID does not match escrow listing" in res.json()["detail"]


def test_confirm_delivery_unauthorized_buyer():
    """Security test: rejects delivery confirmation from unauthorized caller."""
    escrow_id, _ = _create_test_locked_escrow(token_id=310)
    att_payload = make_test_escrow_attestation(token_id=310)

    res = client.post(
        f"/v1/marketplace/escrows/{escrow_id}/confirm-delivery",
        json={
            "buyer_wallet": "0xRogueBuyer000000000000000000000000000099",
            "attestation": att_payload["attestation"],
            "attestation_signature": att_payload["attestation_signature"],
        },
    )
    assert res.status_code == 403
    assert "Unauthorized: Only depositing buyer may confirm delivery" in res.json()["detail"]




