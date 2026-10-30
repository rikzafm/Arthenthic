// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {DeployMainnet} from "../script/DeployMainnet.s.sol";
import {TransferGovernance} from "../script/TransferGovernance.s.sol";
import {ArthenticNFT} from "../src/ArthenticNFT.sol";
import {ArthenticEscrow} from "../src/ArthenticEscrow.sol";
import {MerkleAnchor} from "../src/MerkleAnchor.sol";

interface VmTest {
    function setEnv(string calldata key, string calldata value) external;
    function expectRevert(bytes calldata revertData) external;
    function expectRevert() external;
}

contract DeployHardeningTest {
    VmTest internal constant vm = VmTest(address(uint160(uint256(keccak256("hevm cheat code")))));

    DeployMainnet internal deployScript;
    TransferGovernance internal govScript;

    function setUp() public {
        deployScript = new DeployMainnet();
        govScript    = new TransferGovernance();
    }

    function _setValidDeployEnv() internal {
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x9999999999999999999999999999999999999999");
        vm.setEnv("MAINNET_TIMELOCK", "0x8888888888888888888888888888888888888888");
        vm.setEnv("MAINNET_TREASURY_SAFE", "0x7777777777777777777777777777777777777777");
        vm.setEnv("MAINNET_KMS_SIGNER", "0x6666666666666666666666666666666666666666");
        vm.setEnv("MAINNET_ANCHORER_NODE", "0x00000000000000000000000000000000000000AA");
    }

    function _setValidGovEnv() internal {
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x9999999999999999999999999999999999999999");
        vm.setEnv("MAINNET_TIMELOCK", "0x8888888888888888888888888888888888888888");
        vm.setEnv("MAINNET_NFT_ADDRESS", "0x7777777777777777777777777777777777777777");
        vm.setEnv("MAINNET_ESCROW_ADDRESS", "0x6666666666666666666666666666666666666666");
        vm.setEnv("MAINNET_ANCHOR_ADDRESS", "0x00000000000000000000000000000000000000bb");
    }

    /// @notice Consolidated deployment hardening test: runs sequentially to eliminate parallel test runner races
    function test_DeploymentHardening_ZeroAndPlaceholderReverts_Sequential() public {
        // --- 1. DeployMainnet Zero Address Checks ---
        _setValidDeployEnv();
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("DeployMainnet: MAINNET_GNOSIS_SAFE cannot be zero address"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_TIMELOCK", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("DeployMainnet: MAINNET_TIMELOCK cannot be zero address"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_TREASURY_SAFE", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("DeployMainnet: MAINNET_TREASURY_SAFE cannot be zero address"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_KMS_SIGNER", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("DeployMainnet: MAINNET_KMS_SIGNER cannot be zero address"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_ANCHORER_NODE", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("DeployMainnet: MAINNET_ANCHORER_NODE cannot be zero address"));
        deployScript.run();

        // --- 2. DeployMainnet Placeholder Address Checks ---
        _setValidDeployEnv();
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x1111111111111111111111111111111111111111");
        vm.expectRevert(bytes("DeployMainnet: invalid placeholder gnosisSafe"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_TIMELOCK", "0x2222222222222222222222222222222222222222");
        vm.expectRevert(bytes("DeployMainnet: invalid placeholder timelock"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_TREASURY_SAFE", "0x3333333333333333333333333333333333333333");
        vm.expectRevert(bytes("DeployMainnet: invalid placeholder treasury"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_KMS_SIGNER", "0x4444444444444444444444444444444444444444");
        vm.expectRevert(bytes("DeployMainnet: invalid placeholder kmsNode"));
        deployScript.run();

        _setValidDeployEnv();
        vm.setEnv("MAINNET_ANCHORER_NODE", "0x5555555555555555555555555555555555555555");
        vm.expectRevert(bytes("DeployMainnet: invalid placeholder anchorer"));
        deployScript.run();

        // --- 3. DeployMainnet Success with Valid Addresses ---
        _setValidDeployEnv();
        (ArthenticNFT nft, ArthenticEscrow escrow, MerkleAnchor anchor) = deployScript.run();
        require(address(nft) != address(0), "NFT deployed");
        require(address(escrow) != address(0), "Escrow deployed");
        require(address(anchor) != address(0), "Anchor deployed");

        // --- 4. TransferGovernance Zero & Placeholder Checks ---
        _setValidGovEnv();
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x0000000000000000000000000000000000000000");
        vm.expectRevert(bytes("TransferGovernance: MAINNET_GNOSIS_SAFE cannot be zero address"));
        govScript.run();

        _setValidGovEnv();
        vm.setEnv("MAINNET_GNOSIS_SAFE", "0x1111111111111111111111111111111111111111");
        vm.expectRevert(bytes("TransferGovernance: invalid placeholder gnosisSafe"));
        govScript.run();

        _setValidGovEnv();
        vm.setEnv("MAINNET_TIMELOCK", "0x2222222222222222222222222222222222222222");
        vm.expectRevert(bytes("TransferGovernance: invalid placeholder timelock"));
        govScript.run();

        _setValidGovEnv();
        vm.setEnv("MAINNET_NFT_ADDRESS", "0xaAaAaAaaAaAaAaaAaAAAAAAAAaaaAaAaAaaAaaAa");
        vm.expectRevert(bytes("TransferGovernance: invalid placeholder nftAddr"));
        govScript.run();

        _setValidGovEnv();
        vm.setEnv("MAINNET_ESCROW_ADDRESS", "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB");
        vm.expectRevert(bytes("TransferGovernance: invalid placeholder escrowAddr"));
        govScript.run();

        _setValidGovEnv();
        vm.setEnv("MAINNET_ANCHOR_ADDRESS", "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC");
        vm.expectRevert(bytes("TransferGovernance: invalid placeholder anchorAddr"));
        govScript.run();

        // --- 5. TransferGovernance Success with Valid Addresses ---
        _setValidGovEnv();
        govScript.run();
    }
}
