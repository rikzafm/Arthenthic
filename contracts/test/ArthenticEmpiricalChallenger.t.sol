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
    function expectRevert(bytes calldata revertData) external;
    function assume(bool condition) external pure;
    function setEnv(string calldata key, string calldata value) external;
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

contract ReentrantAttacker {
    ArthenticEscrow public immutable escrow;
    uint256 public targetListingId;
    enum Action { None, RefundDuringClaim, ClaimDuringClaim, RefundDuringRefund, ClaimDuringRefund }
    Action public targetAction;

    bool public callbackTriggered;
    bool public callFailed;
    bytes4 public capturedRevertSelector;

    // Attestation data for claim attacks
    AttestationVerifier.Attestation public attestation;
    bytes public signature;

    constructor(address payable _escrow) {
        escrow = ArthenticEscrow(_escrow);
    }

    function configureAttack(
        uint256 _listingId,
        Action _action,
        AttestationVerifier.Attestation calldata _att,
        bytes calldata _sig
    ) external {
        targetListingId = _listingId;
        targetAction = _action;
        attestation = _att;
        signature = _sig;
    }

    receive() external payable {
        if (!callbackTriggered) {
            callbackTriggered = true;

            bool success;
            bytes memory returnData;

            if (targetAction == Action.RefundDuringClaim || targetAction == Action.RefundDuringRefund) {
                (success, returnData) = address(escrow).call(
                    abi.encodeWithSelector(escrow.refund.selector, targetListingId)
                );
            } else if (targetAction == Action.ClaimDuringClaim || targetAction == Action.ClaimDuringRefund) {
                (success, returnData) = address(escrow).call(
                    abi.encodeWithSelector(escrow.claim.selector, targetListingId, attestation, signature)
                );
            }

            callFailed = !success;
            if (returnData.length >= 4) {
                bytes4 sel;
                assembly {
                    sel := mload(add(returnData, 32))
                }
                capturedRevertSelector = sel;
            }
        }
    }
}

contract ArthenticEmpiricalChallengerTest {
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

    function _signEscrowAttestation(AttestationVerifier.Attestation memory tapAtt) internal view returns (bytes memory) {
        bytes32 structHash = keccak256(
            abi.encode(
                escrow.ATTESTATION_TYPEHASH(),
                tapAtt.tokenId,
                tapAtt.sunDigest,
                tapAtt.similarityBps,
                tapAtt.deadline,
                tapAtt.nonce
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", escrow.DOMAIN_SEPARATOR(), structHash));
        return _signDigest(NODE_PK, digest);
    }

    function _mintArtwork(bytes32 genesisVec, bytes32 chipHash) internal returns (uint256 tokenId) {
        string memory uri = "ar://challenger_bundle";

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

    // =========================================================================
    // 1. BOUNDARY CONDITIONS & 3-WAY SPLIT SUM IDENTITY
    // =========================================================================

    struct Balances {
        uint256 seller;
        uint256 artist;
        uint256 treasury;
    }

    function _executeAndAssertClaim(uint256 price, string memory label) internal {
        uint256 tokenId = _mintArtwork(
            keccak256(abi.encodePacked(label, "genesis", price)),
            keccak256(abi.encodePacked(label, "chip", price))
        );

        address seller = address(0x5E11E2);
        vm.prank(artist);
        nft.transferFrom(artist, seller, tokenId);

        vm.prank(seller);
        nft.approve(address(escrow), tokenId);

        uint256 listingId;
        {
            uint64 expiry = uint64(block.timestamp + 7 days);
            vm.prank(seller);
            listingId = escrow.createListing(tokenId, address(0), price, expiry);
        }

        require(nft.ownerOf(tokenId) == address(escrow), "Escrow must hold NFT before deposit");
        require(address(escrow).balance == 0, "Escrow balance must be 0 initially");

        // Buyer deposits ETH
        vm.deal(buyer, price);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);

        require(address(escrow).balance == price, "Escrow must hold exact deposit");

        Balances memory beforeBals = Balances({
            seller: seller.balance,
            artist: artist.balance,
            treasury: treasurySafe.balance
        });

        // Claim with Attestation
        {
            AttestationVerifier.Attestation memory tapAtt = AttestationVerifier.Attestation({
                tokenId: tokenId,
                sunDigest: keccak256(abi.encodePacked("sun", label, price)),
                similarityBps: 0,
                deadline: uint64(block.timestamp + 300),
                nonce: keccak256(abi.encodePacked("nonce", label, price))
            });
            bytes memory nodeSig = _signEscrowAttestation(tapAtt);

            vm.prank(buyer);
            escrow.claim(listingId, tapAtt, nodeSig);
        }

        // Verification: 3-way split sums to EXACTLY price
        {
            uint256 expectedRoyalty = (price * 500) / 10_000;
            uint256 expectedTreasury = (price * 150) / 10_000;
            uint256 expectedSellerNet = price - expectedRoyalty - expectedTreasury;

            uint256 sellerDelta   = seller.balance - beforeBals.seller;
            uint256 artistDelta   = artist.balance - beforeBals.artist;
            uint256 treasuryDelta = treasurySafe.balance - beforeBals.treasury;

            require(artistDelta == expectedRoyalty, "Artist royalty mismatch");
            require(treasuryDelta == expectedTreasury, "Treasury fee mismatch");
            require(sellerDelta == expectedSellerNet, "Seller net mismatch");
            require(sellerDelta + artistDelta + treasuryDelta == price, "Invariant: Split sum != price");
        }

        // Verification: Escrow balance is strictly 0
        require(address(escrow).balance == 0, "Invariant: Escrow balance must be strictly 0 after claim");
        require(nft.ownerOf(tokenId) == buyer, "Buyer must own NFT");
    }

    /// @notice Boundary 1: Minimal price (10_000 wei)
    function test_Challenge_Boundary_MinimalPrice_10000wei() public {
        _executeAndAssertClaim(10_000 wei, "min_price_10000");
    }

    /// @notice Boundary 2: Large price (500 ether)
    function test_Challenge_Boundary_LargePrice_500ether() public {
        _executeAndAssertClaim(500 ether, "large_price_500eth");
    }

    /// @notice Boundary 3: Ultra-large price (50,000 ether)
    function test_Challenge_Boundary_UltraLargePrice_50000ether() public {
        _executeAndAssertClaim(50_000 ether, "ultra_large_50000eth");
    }

    /// @notice Boundary 4: 1 wei rounding check
    function test_Challenge_Boundary_1wei_Rounding() public {
        _executeAndAssertClaim(1 wei, "1_wei_test");
    }

    /// @notice Exhaustive Sub-10,000 wei rounding and dust checks:
    ///         Tests 1 wei, 2 wei, 3 wei, 19 wei, 20 wei, 66 wei, 67 wei,
    ///         999 wei, 1000 wei, 9999 wei, 10001 wei
    function test_Challenge_Exhaustive_DustRoundingChecks() public {
        uint256[12] memory testPrices = [
            uint256(1),
            uint256(2),
            uint256(3),
            uint256(19),
            uint256(20),
            uint256(66),
            uint256(67),
            uint256(999),
            uint256(1000),
            uint256(9999),
            uint256(10001),
            uint256(1000001)
        ];

        for (uint256 i = 0; i < testPrices.length; i++) {
            _executeAndAssertClaim(testPrices[i], string(abi.encodePacked("dust_", i)));
        }
    }

    // =========================================================================
    // 2. ESCROW BALANCE STRICTLY 0 AFTER REFUND (ETH & USDC)
    // =========================================================================

    function _executeAndAssertRefund(uint256 price, string memory label) internal {
        uint256 tokenId = _mintArtwork(
            keccak256(abi.encodePacked(label, "genesis", price)),
            keccak256(abi.encodePacked(label, "chip", price))
        );

        address seller = address(0x5E11E2);
        vm.prank(artist);
        nft.transferFrom(artist, seller, tokenId);

        vm.prank(seller);
        nft.approve(address(escrow), tokenId);

        uint64 duration = 7 days;
        uint64 expiry = uint64(block.timestamp + duration);
        vm.prank(seller);
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        // Buyer deposits
        vm.deal(buyer, price);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);
        require(address(escrow).balance == price, "Escrow must hold deposit");

        // Warp past expiry
        vm.warp(block.timestamp + duration + 1);

        uint256 buyerBalBefore = buyer.balance;
        vm.prank(buyer);
        escrow.refund(listingId);

        // Assertions:
        require(buyer.balance - buyerBalBefore == price, "Buyer must receive 100% refund");
        require(nft.ownerOf(tokenId) == seller, "Seller must receive NFT back");
        require(address(escrow).balance == 0, "Invariant: Escrow balance strictly 0 after refund");
    }

    function test_Challenge_Refund_ZeroEscrowBalance_1wei() public {
        _executeAndAssertRefund(1 wei, "refund_1wei");
    }

    function test_Challenge_Refund_ZeroEscrowBalance_10000wei() public {
        _executeAndAssertRefund(10_000 wei, "refund_10000wei");
    }

    function test_Challenge_Refund_ZeroEscrowBalance_500ether() public {
        _executeAndAssertRefund(500 ether, "refund_500ether");
    }

    function test_Challenge_Refund_ZeroEscrowBalance_USDC() public {
        uint256 price = 250_000 * 1e6; // 250,000 USDC
        uint256 tokenId = _mintArtwork(keccak256("usdc_refund_gen"), keccak256("usdc_refund_chip"));

        address seller = address(0x5E11E2);
        vm.prank(artist);
        nft.transferFrom(artist, seller, tokenId);

        vm.prank(seller);
        nft.approve(address(escrow), tokenId);

        uint64 duration = 5 days;
        uint64 expiry = uint64(block.timestamp + duration);
        vm.prank(seller);
        uint256 listingId = escrow.createListing(tokenId, address(usdc), price, expiry);

        usdc.mint(buyer, price);
        vm.prank(buyer);
        usdc.approve(address(escrow), price);
        vm.prank(buyer);
        escrow.deposit(listingId);

        require(usdc.balanceOf(address(escrow)) == price, "Escrow USDC must match deposit");

        vm.warp(block.timestamp + duration + 1);

        uint256 buyerUSDCBefore = usdc.balanceOf(buyer);
        vm.prank(buyer);
        escrow.refund(listingId);

        require(usdc.balanceOf(buyer) - buyerUSDCBefore == price, "Buyer must receive 100% USDC refund");
        require(nft.ownerOf(tokenId) == seller, "Seller must receive NFT back");
        require(usdc.balanceOf(address(escrow)) == 0, "Invariant: Escrow USDC balance strictly 0 after refund");
    }

    // =========================================================================
    // 3. ADVERSARIAL REENTRANCY ATTACKS & REENTRANCY() SELECTOR VERIFICATION
    // =========================================================================

    /// @notice Attack 1: Reentrant Seller attempts refund() during claim() payout
    function test_Challenge_Reentrancy_RefundDuringClaim_RevertsREENTRANCY() public {
        ReentrantAttacker attackerSeller = new ReentrantAttacker(payable(address(escrow)));

        uint256 tokenId = _mintArtwork(keccak256("reent_claim_refund_gen"), keccak256("reent_claim_refund_chip"));

        vm.prank(artist);
        nft.transferFrom(artist, address(attackerSeller), tokenId);

        uint256 price = 5 ether;
        uint64 expiry = uint64(block.timestamp + 3 days);

        vm.prank(address(attackerSeller));
        nft.approve(address(escrow), tokenId);

        vm.prank(address(attackerSeller));
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        AttestationVerifier.Attestation memory emptyAtt;
        attackerSeller.configureAttack(listingId, ReentrantAttacker.Action.RefundDuringClaim, emptyAtt, "");

        // Buyer deposits
        vm.deal(buyer, price);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);

        // Protocol Node attestation
        AttestationVerifier.Attestation memory tapAtt = AttestationVerifier.Attestation({
            tokenId: tokenId,
            sunDigest: keccak256("reent_tap"),
            similarityBps: 0,
            deadline: uint64(block.timestamp + 300),
            nonce: keccak256("reent_nonce")
        });
        bytes memory nodeSig = _signEscrowAttestation(tapAtt);

        // Buyer claims
        vm.prank(buyer);
        escrow.claim(listingId, tapAtt, nodeSig);

        // Verify attacker callback executed and failed with REENTRANCY()
        require(attackerSeller.callbackTriggered(), "Attacker receive callback was not reached");
        require(attackerSeller.callFailed(), "Reentrant call succeeded unexpectedly");
        require(
            attackerSeller.capturedRevertSelector() == ArthenticEscrow.REENTRANCY.selector,
            "Reentrant call must revert with ArthenticEscrow.REENTRANCY.selector"
        );
        require(address(escrow).balance == 0, "Escrow balance must be strictly 0");
        require(nft.ownerOf(tokenId) == buyer, "Buyer must have received the NFT");
    }

    /// @notice Attack 2: Reentrant Seller attempts second claim() during claim() payout
    function test_Challenge_Reentrancy_ClaimDuringClaim_RevertsREENTRANCY() public {
        ReentrantAttacker attackerSeller = new ReentrantAttacker(payable(address(escrow)));

        uint256 tokenId = _mintArtwork(keccak256("reent_claim_claim_gen"), keccak256("reent_claim_claim_chip"));

        vm.prank(artist);
        nft.transferFrom(artist, address(attackerSeller), tokenId);

        uint256 price = 2 ether;
        uint64 expiry = uint64(block.timestamp + 3 days);

        vm.prank(address(attackerSeller));
        nft.approve(address(escrow), tokenId);

        vm.prank(address(attackerSeller));
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        // Node attestation
        AttestationVerifier.Attestation memory tapAtt = AttestationVerifier.Attestation({
            tokenId: tokenId,
            sunDigest: keccak256("reent_claim_tap"),
            similarityBps: 0,
            deadline: uint64(block.timestamp + 300),
            nonce: keccak256("reent_claim_nonce")
        });
        bytes memory nodeSig = _signEscrowAttestation(tapAtt);

        // Configure attacker to call claim() recursively during payout
        attackerSeller.configureAttack(listingId, ReentrantAttacker.Action.ClaimDuringClaim, tapAtt, nodeSig);

        vm.deal(buyer, price);
        vm.prank(buyer);
        escrow.deposit{value: price}(listingId);

        vm.prank(buyer);
        escrow.claim(listingId, tapAtt, nodeSig);

        require(attackerSeller.callbackTriggered(), "Attacker callback was not reached");
        require(attackerSeller.callFailed(), "Recursive claim succeeded unexpectedly");
        require(
            attackerSeller.capturedRevertSelector() == ArthenticEscrow.REENTRANCY.selector,
            "Recursive claim must revert with REENTRANCY selector"
        );
        require(address(escrow).balance == 0, "Escrow balance must be 0");
    }

    /// @notice Attack 3: Reentrant Buyer attempts refund() during refund() payout
    function test_Challenge_Reentrancy_RefundDuringRefund_RevertsREENTRANCY() public {
        ReentrantAttacker attackerBuyer = new ReentrantAttacker(payable(address(escrow)));

        uint256 tokenId = _mintArtwork(keccak256("reent_ref_ref_gen"), keccak256("reent_ref_ref_chip"));

        address seller = address(0x5E11E2);
        vm.prank(artist);
        nft.transferFrom(artist, seller, tokenId);

        uint256 price = 10 ether;
        uint64 duration = 2 days;
        uint64 expiry = uint64(block.timestamp + duration);

        vm.prank(seller);
        nft.approve(address(escrow), tokenId);

        vm.prank(seller);
        uint256 listingId = escrow.createListing(tokenId, address(0), price, expiry);

        AttestationVerifier.Attestation memory emptyAtt;
        attackerBuyer.configureAttack(listingId, ReentrantAttacker.Action.RefundDuringRefund, emptyAtt, "");

        // Attacker Buyer deposits
        vm.deal(address(attackerBuyer), price);
        vm.prank(address(attackerBuyer));
        escrow.deposit{value: price}(listingId);

        // Advance past expiry
        vm.warp(block.timestamp + duration + 1);

        // Attacker buyer triggers refund
        vm.prank(address(attackerBuyer));
        escrow.refund(listingId);

        require(attackerBuyer.callbackTriggered(), "Attacker callback was not reached");
        require(attackerBuyer.callFailed(), "Recursive refund call succeeded unexpectedly");
        require(
            attackerBuyer.capturedRevertSelector() == ArthenticEscrow.REENTRANCY.selector,
            "Recursive refund must revert with REENTRANCY selector"
        );
        require(address(escrow).balance == 0, "Escrow balance must be 0");
        require(nft.ownerOf(tokenId) == seller, "Seller must receive NFT back");
    }
}
