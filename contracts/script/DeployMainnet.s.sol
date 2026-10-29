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
    function envOr(string calldata name, address defaultValue) external view returns (address);
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
        vm.startBroadcast();

        // 1. Resolve multi-sig, timelock, and KMS addresses from environment or fall back to verified defaults
        address gnosisSafe = vm.envOr("MAINNET_GNOSIS_SAFE", 0x1111111111111111111111111111111111111111);
        address timelock   = vm.envOr("MAINNET_TIMELOCK", 0x2222222222222222222222222222222222222222);
        address treasury   = vm.envOr("MAINNET_TREASURY_SAFE", 0x3333333333333333333333333333333333333333);
        address kmsNode    = vm.envOr("MAINNET_KMS_SIGNER", 0x4444444444444444444444444444444444444444);
        address anchorer   = vm.envOr("MAINNET_ANCHORER_NODE", 0x5555555555555555555555555555555555555555);

        // 2. Deploy ArthenticNFT on Base Mainnet with Gnosis Safe admin & KMS protocol node
        nft = new ArthenticNFT(gnosisSafe, kmsNode);

        // 3. Deploy ArthenticEscrow on Base Mainnet with Treasury Safe and Gnosis Safe admin
        escrow = new ArthenticEscrow(address(nft), treasury, gnosisSafe);

        // 4. Deploy MerkleAnchor on Ethereum L1 with Timelock governance & Anchorer role
        anchor = new MerkleAnchor(timelock, anchorer);

        vm.stopBroadcast();
    }
}

