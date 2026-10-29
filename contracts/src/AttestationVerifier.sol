// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "./Roles.sol";

/// @title AttestationVerifier
/// @notice Abstract EIP-712 attestation verifier inherited by ArthenticNFT and ArthenticEscrow.
/// Enforces Protocol Node cryptographic signatures, short validity windows, anti-replay nonces,
/// and the 8800 bps (88.0%) optical LiDAR threshold.
abstract contract AttestationVerifier {
    uint16 public constant MIN_SIMILARITY_BPS = 8800; // 88.0% threshold (D-06, ADR-06)

    // Struct matching server/crypto/attestation.py and UML Part 1 UC-D/SD-06
    struct Attestation {
        uint256 tokenId;
        bytes32 sunDigest;      // keccak256(abi.encodePacked(uid, ":", ctr, ":", cmac))
        uint16 similarityBps;   // 0 for Level 1 NFC tap; 8800..10000 for Level 2 Optical LiDAR
        uint256 deadline;       // block.timestamp validity window (typically now + 300s)
        bytes32 nonce;          // single-use anti-replay nonce
    }

    bytes32 public constant ATTESTATION_TYPEHASH = keccak256(
        "Attestation(uint256 tokenId,bytes32 sunDigest,uint16 similarityBps,uint256 deadline,bytes32 nonce)"
    );

    bytes32 public immutable DOMAIN_SEPARATOR;

    // Single-use anti-replay mapping
    mapping(bytes32 => bool) public usedNonce;

    // Custom errors
    error ATTESTATION_EXPIRED();
    error REPLAY();
    error SIMILARITY_BELOW_THRESHOLD();
    error INVALID_SIGNER();
    error ACCESS_DENIED();

    event AttestationVerified(
        uint256 indexed tokenId,
        bytes32 indexed nonce,
        uint16 similarityBps,
        address signer
    );

    constructor(string memory name, string memory version) {
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                block.chainid,
                address(this)
            )
        );
    }

    /// @notice Virtual method to check role assignments, implemented via AccessControl
    function hasRole(bytes32 role, address account) public view virtual returns (bool);

    /// @notice Internal verification of an EIP-712 Protocol Node Attestation
    function _verifyAttestation(
        Attestation calldata a,
        bytes calldata sig,
        bool requireOptical
    ) internal returns (address signer) {
        if (block.timestamp > a.deadline) revert ATTESTATION_EXPIRED();
        if (usedNonce[a.nonce]) revert REPLAY();
        if (requireOptical && a.similarityBps < MIN_SIMILARITY_BPS) revert SIMILARITY_BELOW_THRESHOLD();

        // Compute EIP-712 digest
        bytes32 structHash = keccak256(
            abi.encode(
                ATTESTATION_TYPEHASH,
                a.tokenId,
                a.sunDigest,
                a.similarityBps,
                a.deadline,
                a.nonce
            )
        );

        bytes32 digest = keccak256(
            abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash)
        );

        signer = _recoverSigner(digest, sig);
        if (!hasRole(Roles.PROTOCOL_NODE_ROLE, signer)) revert INVALID_SIGNER();

        // Mark nonce used before any external interaction
        usedNonce[a.nonce] = true;
        emit AttestationVerified(a.tokenId, a.nonce, a.similarityBps, signer);
    }

    function _recoverSigner(bytes32 hash, bytes calldata sig) internal pure returns (address) {
        if (sig.length != 65) revert INVALID_SIGNER();
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) revert INVALID_SIGNER();
        if (v != 27 && v != 28) revert INVALID_SIGNER();
        address recovered = ecrecover(hash, v, r, s);
        if (recovered == address(0)) revert INVALID_SIGNER();
        return recovered;
    }
}

