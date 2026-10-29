// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "../src/Roles.sol";
import {ArthenticNFT} from "../src/ArthenticNFT.sol";
import {ArthenticEscrow} from "../src/ArthenticEscrow.sol";
import {MerkleAnchor} from "../src/MerkleAnchor.sol";

interface VmScript {
    function startBroadcast() external;
    function stopBroadcast() external;
}

/// @title DeployArthentic
/// @notice Deterministic deployment script for Anvil, Base Sepolia (84532), and Ethereum Sepolia (11155111).
/// Usage: forge script script/Deploy.s.sol:DeployArthentic --rpc-url http://127.0.0.1:8545 --broadcast
contract DeployArthentic {
    VmScript internal constant vm = VmScript(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run()
        external
        returns (ArthenticNFT nft, ArthenticEscrow escrow, MerkleAnchor anchor)
    {
        vm.startBroadcast();

        address admin = msg.sender;
        address protocolNode = msg.sender;
        address treasurySafe = msg.sender;

        nft = new ArthenticNFT(admin, protocolNode);
        nft.grantRole(Roles.VERIFIER_ROLE, admin);
        nft.grantRole(Roles.ARTIST_ROLE, admin);
        nft.grantRole(Roles.CONSERVATOR_ROLE, admin);

        escrow = new ArthenticEscrow(address(nft), treasurySafe, admin);
        anchor = new MerkleAnchor(admin, admin);

        vm.stopBroadcast();
    }
}

