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

/// @title TransferGovernance
/// @notice Wave 3 Milestone 7 Production Governance Decentralization Script.
/// Transfers administrative authority over ArthenticNFT and ArthenticEscrow on Base Mainnet
/// to the 3-of-5 Gnosis Safe, transfers MerkleAnchor on Ethereum L1 to the 48h Timelock,
/// and revokes all deployer administrative roles.
/// Usage: forge script script/TransferGovernance.s.sol:TransferGovernance --rpc-url $BASE_MAINNET_RPC --broadcast
contract TransferGovernance {
    VmScript internal constant vm = VmScript(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external {
        address gnosisSafe = vm.envAddress("MAINNET_GNOSIS_SAFE");
        address timelock   = vm.envAddress("MAINNET_TIMELOCK");
        address nftAddr    = vm.envAddress("MAINNET_NFT_ADDRESS");
        address escrowAddr = vm.envAddress("MAINNET_ESCROW_ADDRESS");
        address anchorAddr = vm.envAddress("MAINNET_ANCHOR_ADDRESS");

        // Fail-fast assertions against zero-address or placeholder burn addresses
        require(gnosisSafe != address(0), "TransferGovernance: MAINNET_GNOSIS_SAFE cannot be zero address");
        require(timelock   != address(0), "TransferGovernance: MAINNET_TIMELOCK cannot be zero address");
        require(nftAddr    != address(0), "TransferGovernance: MAINNET_NFT_ADDRESS cannot be zero address");
        require(escrowAddr != address(0), "TransferGovernance: MAINNET_ESCROW_ADDRESS cannot be zero address");
        require(anchorAddr != address(0), "TransferGovernance: MAINNET_ANCHOR_ADDRESS cannot be zero address");

        require(gnosisSafe != 0x1111111111111111111111111111111111111111, "TransferGovernance: invalid placeholder gnosisSafe");
        require(timelock   != 0x2222222222222222222222222222222222222222, "TransferGovernance: invalid placeholder timelock");
        require(nftAddr    != 0xaAaAaAaaAaAaAaaAaAAAAAAAAaaaAaAaAaaAaaAa, "TransferGovernance: invalid placeholder nftAddr");
        require(escrowAddr != 0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB, "TransferGovernance: invalid placeholder escrowAddr");
        require(anchorAddr != 0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC, "TransferGovernance: invalid placeholder anchorAddr");

        vm.startBroadcast();

        // 1. Transfer ArthenticNFT admin role to Gnosis Safe & revoke deployer
        if (nftAddr.code.length > 0) {
            ArthenticNFT nft = ArthenticNFT(nftAddr);
            bytes32 adminRole = nft.DEFAULT_ADMIN_ROLE();
            if (!nft.hasRole(adminRole, gnosisSafe)) {
                nft.grantRole(adminRole, gnosisSafe);
            }
            if (nft.hasRole(adminRole, msg.sender) && msg.sender != gnosisSafe) {
                nft.revokeRole(adminRole, msg.sender);
            }
        }

        // 2. Transfer ArthenticEscrow admin to Gnosis Safe
        if (escrowAddr.code.length > 0) {
            ArthenticEscrow escrow = ArthenticEscrow(escrowAddr);
            if (escrow.admin() == msg.sender && msg.sender != gnosisSafe) {
                escrow.transferAdmin(gnosisSafe);
            }
        }

        // 3. Transfer MerkleAnchor admin role to Timelock & revoke deployer
        if (anchorAddr.code.length > 0) {
            MerkleAnchor anchor = MerkleAnchor(anchorAddr);
            bytes32 adminRole = anchor.DEFAULT_ADMIN_ROLE();
            if (!anchor.hasRole(adminRole, timelock)) {
                anchor.grantRole(adminRole, timelock);
            }
            if (anchor.hasRole(adminRole, msg.sender) && msg.sender != timelock) {
                anchor.revokeRole(adminRole, msg.sender);
            }
        }

        vm.stopBroadcast();
    }
}

