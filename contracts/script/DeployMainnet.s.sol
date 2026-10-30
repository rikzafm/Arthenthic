// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "../src/Roles.sol";
import {ArthenticNFT} from "../src/ArthenticNFT.sol";
import {ArthenticEscrow} from "../src/ArthenticEscrow.sol";
import {MerkleAnchor} from "../src/MerkleAnchor.sol";

interface VmScript {
    function startBroadcast() external;
    function stopBroadcast() external;
    function envAddress(string calldata name) external view returns (address);
}

/// @title DeployMainnet
/// @notice Wave 3 Milestone 6 Production Mainnet Deployment Script for Base Mainnet (8453)
///         and Ethereum Mainnet (1) behind Gnosis Safe multisig (3-of-5) & Timelock.
/// Usage: forge script script/DeployMainnet.s.sol:DeployMainnet --rpc-url $BASE_MAINNET_RPC --broadcast --verify
contract DeployMainnet {
    VmScript internal constant vm = VmScript(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run()
        external
        returns (ArthenticNFT nft, ArthenticEscrow escrow, MerkleAnchor anchor)
    {
        // 1. Resolve multi-sig, timelock, and KMS addresses strictly from environment (no fallback defaults)
        address gnosisSafe = vm.envAddress("MAINNET_GNOSIS_SAFE");
        address timelock   = vm.envAddress("MAINNET_TIMELOCK");
        address treasury   = vm.envAddress("MAINNET_TREASURY_SAFE");
        address kmsNode    = vm.envAddress("MAINNET_KMS_SIGNER");
        address anchorer   = vm.envAddress("MAINNET_ANCHORER_NODE");

        // 2. Fail-fast assertions against zero-address or placeholder burn addresses
        require(gnosisSafe != address(0), "DeployMainnet: MAINNET_GNOSIS_SAFE cannot be zero address");
        require(timelock != address(0), "DeployMainnet: MAINNET_TIMELOCK cannot be zero address");
        require(treasury != address(0), "DeployMainnet: MAINNET_TREASURY_SAFE cannot be zero address");
        require(kmsNode != address(0), "DeployMainnet: MAINNET_KMS_SIGNER cannot be zero address");
        require(anchorer != address(0), "DeployMainnet: MAINNET_ANCHORER_NODE cannot be zero address");

        require(gnosisSafe != 0x1111111111111111111111111111111111111111, "DeployMainnet: invalid placeholder gnosisSafe");
        require(timelock   != 0x2222222222222222222222222222222222222222, "DeployMainnet: invalid placeholder timelock");
        require(treasury   != 0x3333333333333333333333333333333333333333, "DeployMainnet: invalid placeholder treasury");
        require(kmsNode    != 0x4444444444444444444444444444444444444444, "DeployMainnet: invalid placeholder kmsNode");
        require(anchorer   != 0x5555555555555555555555555555555555555555, "DeployMainnet: invalid placeholder anchorer");

        // 3. Begin broadcast only after all addresses are validated
        vm.startBroadcast();

        // 4. Deploy ArthenticNFT on Base Mainnet with Gnosis Safe admin & KMS protocol node
        nft = new ArthenticNFT(gnosisSafe, kmsNode);

        // 5. Deploy ArthenticEscrow on Base Mainnet with Treasury Safe and Gnosis Safe admin
        escrow = new ArthenticEscrow(address(nft), treasury, gnosisSafe);

        // 6. Deploy MerkleAnchor on Ethereum L1 with Timelock governance & Anchorer role
        anchor = new MerkleAnchor(timelock, anchorer);

        vm.stopBroadcast();
    }
}

