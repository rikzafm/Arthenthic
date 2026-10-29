// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

library Roles {
    bytes32 internal constant ARTIST_ROLE        = keccak256("ARTIST_ROLE");
    bytes32 internal constant VERIFIER_ROLE      = keccak256("VERIFIER_ROLE");
    bytes32 internal constant CONSERVATOR_ROLE   = keccak256("CONSERVATOR_ROLE");
    bytes32 internal constant PROTOCOL_NODE_ROLE = keccak256("PROTOCOL_NODE_ROLE");
    bytes32 internal constant ANCHORER_ROLE      = keccak256("ANCHORER_ROLE");
}

