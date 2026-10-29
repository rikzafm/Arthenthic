// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "../src/Roles.sol";
import {AttestationVerifier} from "../src/AttestationVerifier.sol";
import {ArthenticNFT} from "../src/ArthenticNFT.sol";
import {ArthenticEscrow, IERC20} from "../src/ArthenticEscrow.sol";
import {MerkleAnchor} from "../src/MerkleAnchor.sol";

interface Vm {
    function addr(uint256 privateKey) external pure returns (address);
    function sign(uint256 privateKey, bytes32 digest) external pure returns (uint8 v, bytes32 r, bytes32 s);
    function prank(address msgSender) external;
    function deal(address who, uint256 newBalance) external;
    function warp(uint256 newTimestamp) external;
    function expectRevert(bytes4 revertData) external;
}

contract MockUSDC is IERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external override returns (bool) {
        require(balanceOf[msg.sender] >= amount, "INSUFFICIENT_BALANCE");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        require(balanceOf[from] >= amount, "INSUFFICIENT_BALANCE");
        require(allowance[from][msg.sender] >= amount, "INSUFFICIENT_ALLOWANCE");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract ArthenticProtocolTest {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    uint256 internal constant ADMIN_PK       = 0xA11CE;
    uint256 internal constant NODE_PK        = 0xB0B01;
    uint256 internal constant ARTIST_PK      = 0xA27157;
    uint256 internal constant VERIFIER_PK    = 0x7E21F;
    uint256 internal constant CONSERVATOR_PK = 0xC045E;
    uint256 internal constant BUYER_PK       = 0xB07E2;
    uint256 internal constant ANCHORER_PK    = 0xA4C02;

    address internal admin;
    address internal protocolNode;
    address internal artist;
    address internal verifier;
    address internal conservator;
    address internal buyer;
    address internal treasurySafe;
    address internal anchorer;

    ArthenticNFT internal nft;
    ArthenticEscrow internal escrow;
    MerkleAnchor internal anchor;
    MockUSDC internal usdc;

    function setUp() public {
        admin        = vm.addr(ADMIN_PK);
        protocolNode = vm.addr(NODE_PK);
        artist       = vm.addr(ARTIST_PK);
        verifier     = vm.addr(VERIFIER_PK);
        conservator  = vm.addr(CONSERVATOR_PK);
        buyer        = vm.addr(BUYER_PK);
        anchorer     = vm.addr(ANCHORER_PK);
        treasurySafe = address(0x9999);

        vm.prank(admin);
        nft = new ArthenticNFT(admin, protocolNode);

        vm.prank(admin);
        nft.grantRole(Roles.ARTIST_ROLE, artist);
        vm.prank(admin);
        nft.grantRole(Roles.VERIFIER_ROLE, verifier);
        vm.prank(admin);
        nft.grantRole(Roles.CONSERVATOR_ROLE, conservator);

        escrow = new ArthenticEscrow(address(nft), treasurySafe, admin);
        anchor = new MerkleAnchor(admin, anchorer);
        usdc   = new MockUSDC();
    }

    function _signDigest(uint256 pk, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _mintSampleArtwork() internal returns (uint256 tokenId, bytes32 genesisVec, bytes32 chipHash) {
        genesisVec = keccak256("384d_lidar_macro_vector_v1");
        chipHash   = keccak256("04A1B2C3D4E580");
        string memory uri = "ar://arthentic_genesis_bundle_1";

        bytes32 dossierDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                nft.DOMAIN_SEPARATOR(),
                keccak256(
                    abi.encode(
                        nft.GENESIS_DOSSIER_TYPEHASH(),
                        artist,
                        genesisVec,
                        chipHash,
                        keccak256(bytes(uri))
                    )
                )
            )
        );
        bytes memory artistSig = _signDigest(ARTIST_PK, dossierDigest);

        vm.prank(verifier);
        tokenId = nft.genesisMint(artist, genesisVec, chipHash, uri, artistSig);
    }

    function test_GenesisMint_And_ADR02_ArtistCoSign() public {
        (uint256 tokenId, bytes32 genesisVec, bytes32 chipHash) = _mintSampleArtwork();
        require(tokenId == 1, "Token ID must be 1");
        require(nft.ownerOf(tokenId) == artist, "Owner must be artist");
        require(nft.genesisHash(tokenId) == genesisVec, "Genesis hash mismatch");
        require(nft.activeChip(tokenId) == chipHash, "Active chip mismatch");
        require(nft.chipBound(chipHash), "Chip must be bound");

        (address receiver, uint256 royaltyAmt) = nft.royaltyInfo(tokenId, 10000);
        require(receiver == artist && royaltyAmt == 500, "ERC-2981 5% royalty mismatch");
    }

    function test_RevertWhen_DuplicateChipBound_SC_CHIP_01() public {
        (, bytes32 genesisVec, bytes32 chipHash) = _mintSampleArtwork();
        string memory uri = "ar://arthentic_genesis_bundle_2";

        bytes32 dossierDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                nft.DOMAIN_SEPARATOR(),
                keccak256(
                    abi.encode(
                        nft.GENESIS_DOSSIER_TYPEHASH(),
                        artist,
                        genesisVec,
                        chipHash,
                        keccak256(bytes(uri))
                    )
                )
            )
        );
        bytes memory artistSig = _signDigest(ARTIST_PK, dossierDigest);

        vm.prank(verifier);
        vm.expectRevert(ArthenticNFT.CHIP_ALREADY_BOUND.selector);
        nft.genesisMint(artist, genesisVec, chipHash, uri, artistSig);
    }

    function test_UpdateCondition_ADR03_OwnerConsent_And_ImmutableGenesis_SC_GEN_01() public {
        (uint256 tokenId, bytes32 originalGenesis, ) = _mintSampleArtwork();

        bytes32 newVec = keccak256("post_restoration_vector_v2");
        string memory noteURI = "ar://restoration_report_v2";

        bytes32 consentDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                nft.DOMAIN_SEPARATOR(),
                keccak256(
                    abi.encode(
                        nft.OWNER_CONSENT_TYPEHASH(),
                        tokenId,
                        newVec,
                        keccak256(bytes(noteURI)),
                        tokenId
                    )
                )
            )
        );
        bytes memory ownerSig = _signDigest(ARTIST_PK, consentDigest);

        vm.prank(conservator);
        nft.updateCondition(tokenId, newVec, noteURI, ownerSig);

        // SC-GEN-01: genesisHash must remain strictly unchanged
        require(nft.genesisHash(tokenId) == originalGenesis, "SC-GEN-01 violated: genesisHash mutated");
    }

    function test_ReplaceChip_F05_3of3Approvals_And_OpticalGate() public {
        (uint256 tokenId, , bytes32 oldChip) = _mintSampleArtwork();

        // Transfer artwork to Collector (buyer) so Owner != Artist
        vm.prank(artist);
        nft.transferFrom(artist, buyer, tokenId);

        bytes32 newChip = keccak256("04NEWCHIP99999");
        AttestationVerifier.Attestation memory optical = AttestationVerifier.Attestation({
            tokenId: tokenId,
            sunDigest: keccak256("optical_surface_match_9420bps"),
            similarityBps: 9420,
            deadline: uint64(block.timestamp + 300),
            nonce: bytes32(uint256(777))
        });

        bytes32 attStructHash = keccak256(
            abi.encode(
                nft.ATTESTATION_TYPEHASH(),
                optical.tokenId,
                optical.sunDigest,
                optical.similarityBps,
                optical.deadline,
                optical.nonce
            )
        );
        bytes32 attDigest = keccak256(abi.encodePacked("\x19\x01", nft.DOMAIN_SEPARATOR(), attStructHash));
        bytes memory nodeSig = _signDigest(NODE_PK, attDigest);

        bytes32 repDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                nft.DOMAIN_SEPARATOR(),
                keccak256(
                    abi.encode(
                        nft.CHIP_REPLACEMENT_TYPEHASH(),
                        tokenId,
                        oldChip,
                        newChip,
                        optical.sunDigest
                    )
                )
            )
        );

        bytes[3] memory approvals = [
            _signDigest(BUYER_PK, repDigest),    // 1/3 Collector (current owner)
            _signDigest(ARTIST_PK, repDigest),   // 2/3 Original Artist
            _signDigest(VERIFIER_PK, repDigest)  // 3/3 Verifier Gallery
        ];

        vm.prank(verifier);
        nft.replaceChip(tokenId, newChip, optical, nodeSig, approvals);

        require(!nft.chipBound(oldChip), "Old chip should be unbound");
        require(nft.chipBound(newChip), "New chip should be bound");
        require(nft.activeChip(tokenId) == newChip, "Active chip should be updated");
    }

    function test_Escrow_ETH_Settlement_ADR04_ADR05_935_50_15_Split() public {
        (uint256 tokenId, , ) = _mintSampleArtwork();

        // Artist transfers to a collector who then lists it, or Artist lists directly
        uint256 price = 10 ether;
        uint64 expiry = uint64(block.timestamp + 14 days);

        vm.prank(artist);
        nft.approve(address(escrow), tokenId);

        vm.prank(artist);
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        vm.deal(buyer, 10 ether);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);

        AttestationVerifier.Attestation memory tapAtt = AttestationVerifier.Attestation({
            tokenId: tokenId,
            sunDigest: keccak256("nfc_sun_tap_arrival"),
            similarityBps: 0,
            deadline: uint64(block.timestamp + 300),
            nonce: bytes32(uint256(888))
        });

        bytes32 attStructHash = keccak256(
            abi.encode(
                escrow.ATTESTATION_TYPEHASH(),
                tapAtt.tokenId,
                tapAtt.sunDigest,
                tapAtt.similarityBps,
                tapAtt.deadline,
                tapAtt.nonce
            )
        );
        bytes32 attDigest = keccak256(abi.encodePacked("\x19\x01", escrow.DOMAIN_SEPARATOR(), attStructHash));
        bytes memory nodeSig = _signDigest(NODE_PK, attDigest);

        uint256 artistBalBefore = artist.balance;
        uint256 safeBalBefore   = treasurySafe.balance;

        vm.prank(buyer);
        escrow.claim(listingId, tapAtt, nodeSig);

        require(nft.ownerOf(tokenId) == buyer, "Buyer must own NFT after claim");
        // Since artist is both seller (93.5%) and royalty recipient (5.0%), artist receives 98.5% = 9.85 ETH
        require(artist.balance - artistBalBefore == 9.85 ether, "Artist/Seller payout mismatch");
        require(treasurySafe.balance - safeBalBefore == 0.15 ether, "Treasury 1.5% fee mismatch");
    }

    function test_Escrow_USDC_Settlement_ADR04_ADR05() public {
        (uint256 tokenId, , ) = _mintSampleArtwork();
        address seller = address(0x5E11E2);

        // Transfer NFT from artist to seller so seller != artist
        vm.prank(artist);
        nft.transferFrom(artist, seller, tokenId);

        uint256 price = 10_000 * 1e6; // 10,000 USDC
        uint64 expiry = uint64(block.timestamp + 14 days);

        vm.prank(seller);
        nft.approve(address(escrow), tokenId);
        vm.prank(seller);
        uint256 listingId = escrow.createListing(tokenId, address(usdc), price, expiry);

        usdc.mint(buyer, price);
        vm.prank(buyer);
        usdc.approve(address(escrow), price);
        vm.prank(buyer);
        escrow.deposit(listingId);

        AttestationVerifier.Attestation memory tapAtt = AttestationVerifier.Attestation({
            tokenId: tokenId,
            sunDigest: keccak256("nfc_sun_tap_usdc"),
            similarityBps: 0,
            deadline: uint64(block.timestamp + 300),
            nonce: bytes32(uint256(889))
        });
        bytes32 attStructHash = keccak256(
            abi.encode(
                escrow.ATTESTATION_TYPEHASH(),
                tapAtt.tokenId,
                tapAtt.sunDigest,
                tapAtt.similarityBps,
                tapAtt.deadline,
                tapAtt.nonce
            )
        );
        bytes32 attDigest = keccak256(abi.encodePacked("\x19\x01", escrow.DOMAIN_SEPARATOR(), attStructHash));
        bytes memory nodeSig = _signDigest(NODE_PK, attDigest);

        vm.prank(buyer);
        escrow.claim(listingId, tapAtt, nodeSig);

        require(usdc.balanceOf(seller) == 9_350 * 1e6, "Seller 93.5% USDC mismatch");
        require(usdc.balanceOf(artist) == 500 * 1e6, "Artist 5.0% USDC royalty mismatch");
        require(usdc.balanceOf(treasurySafe) == 150 * 1e6, "Treasury 1.5% USDC fee mismatch");
        require(nft.ownerOf(tokenId) == buyer, "Buyer must own NFT");
    }

    function test_Escrow_PostExpiry_AutoRefund_C12() public {
        (uint256 tokenId, , ) = _mintSampleArtwork();
        uint256 price = 2 ether;
        uint64 expiry = uint64(block.timestamp + 7 days);

        vm.prank(artist);
        nft.approve(address(escrow), tokenId);
        vm.prank(artist);
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        vm.deal(buyer, price);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);

        // Warp past expiry
        vm.warp(block.timestamp + 8 days);

        uint256 buyerBalBefore = buyer.balance;
        vm.prank(buyer);
        escrow.refund(listingId);

        require(buyer.balance - buyerBalBefore == price, "Buyer must receive 100% refund");
        require(nft.ownerOf(tokenId) == artist, "Seller must receive NFT back");
    }

    function test_MerkleAnchor_H05_RootAnchored() public {
        bytes32 root = keccak256("batch_merkle_root_001");
        vm.prank(anchorer);
        anchor.anchorRoot(root, 100, 200);

        require(anchor.isAnchored(root), "Root must be marked anchored");
        require(anchor.totalAnchoredRoots() == 1, "Total anchored roots must be 1");
    }
}
