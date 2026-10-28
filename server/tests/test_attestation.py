import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from server.crypto.attestation import (
    AttestationSigner,
    TEST_SIGNER_PRIVATE_KEY,
    ATTESTATION_DOMAIN,
    ATTESTATION_TYPES
)

def test_attestation_signing_and_recovery():
    signer = AttestationSigner(TEST_SIGNER_PRIVATE_KEY)

    token_id = 101
    sun_digest = signer.compute_sun_digest("04A1B2C3D4", 42, "CMAC1234")
    similarity_bps = 9200

    attestation = signer.create_attestation(token_id, sun_digest, similarity_bps)

    assert attestation["tokenId"] == "101"
    assert attestation["similarityBps"] == 9200
    assert attestation["signer"] == signer.address
    assert attestation["signature"].startswith("0x")

    # Recover signer from EIP-712 typed data
    message_data = {
        "tokenId": token_id,
        "sunDigest": sun_digest,
        "similarityBps": similarity_bps,
        "deadline": attestation["deadline"],
        "nonce": attestation["nonce"]
    }

    signable = encode_typed_data(
        domain_data=ATTESTATION_DOMAIN,
        message_types={"Attestation": ATTESTATION_TYPES["Attestation"]},
        message_data=message_data
    )

    recovered = Account.recover_message(signable, signature=attestation["signature"])
    assert recovered.lower() == signer.address.lower()

def test_nonce_uniqueness():
    signer = AttestationSigner(TEST_SIGNER_PRIVATE_KEY)
    att1 = signer.create_attestation(101, "0x" + "1" * 64, 9000)
    att2 = signer.create_attestation(101, "0x" + "1" * 64, 9000)
    assert att1["nonce"] != att2["nonce"]

