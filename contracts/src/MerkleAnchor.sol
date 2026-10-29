// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "./Roles.sol";

/// @title MerkleAnchor
/// @notice Ethereum L1 Settlement Anchor for Base L2 Provenance Events (H-05 / SD-10).
/// Stores periodic Merkle roots covering batched L2 authenticity events, enabling
/// cryptographic inclusion proofs directly against Ethereum L1 security.
contract MerkleAnchor {
    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;
    mapping(bytes32 => mapping(address => bool)) private _roles;

    uint256 public totalAnchoredRoots;
    mapping(bytes32 => bool) public isAnchored;
    mapping(uint256 => bytes32) public batchRoots;

    event RootAnchored(
        bytes32 indexed root,
        uint64 fromBlock,
        uint64 toBlock,
        uint64 timestamp
    );
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);

    error ACCESS_DENIED();
    error INVALID_ROOT();
    error ALREADY_ANCHORED();

    modifier onlyRole(bytes32 role) {
        if (!_roles[role][msg.sender] && !_roles[DEFAULT_ADMIN_ROLE][msg.sender]) {
            revert ACCESS_DENIED();
        }
        _;
    }

    constructor(address initialAdmin, address anchorer) {
        _roles[DEFAULT_ADMIN_ROLE][initialAdmin] = true;
        _roles[Roles.ANCHORER_ROLE][anchorer] = true;
        emit RoleGranted(DEFAULT_ADMIN_ROLE, initialAdmin, msg.sender);
        emit RoleGranted(Roles.ANCHORER_ROLE, anchorer, msg.sender);
    }

    function hasRole(bytes32 role, address account) public view returns (bool) {
        return _roles[role][account] || _roles[DEFAULT_ADMIN_ROLE][account];
    }

    function grantRole(bytes32 role, address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _roles[role][account] = true;
        emit RoleGranted(role, account, msg.sender);
    }

    function revokeRole(bytes32 role, address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _roles[role][account] = false;
        emit RoleRevoked(role, account, msg.sender);
    }

    /// @notice H-05: Anchor a new Merkle root of batched Base L2 provenance events onto Ethereum L1
    function anchorRoot(bytes32 root, uint64 fromBlock, uint64 toBlock)
        external
        onlyRole(Roles.ANCHORER_ROLE)
    {
        if (root == bytes32(0)) revert INVALID_ROOT();
        if (isAnchored[root]) revert ALREADY_ANCHORED();

        isAnchored[root] = true;
        batchRoots[totalAnchoredRoots++] = root;

        // casting to 'uint64' is safe because block.timestamp fits in uint64 for thousands of years
        // forge-lint: disable-next-line(unsafe-typecast)
        emit RootAnchored(root, fromBlock, toBlock, uint64(block.timestamp));
    }
}

