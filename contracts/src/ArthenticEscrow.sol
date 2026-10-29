// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "./Roles.sol";
import {AttestationVerifier} from "./AttestationVerifier.sol";
import {ArthenticNFT} from "./ArthenticNFT.sol";

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title ArthenticEscrow
/// @notice Base L2 Custodial Escrow & Settlement Engine (UC-C).
/// Enforces:
/// - ADR-04: Dual Asset Settlement (Native Base ETH or USDC)
/// - ADR-05: Atomic 3-Way Split (93.5% Seller, 5.0% Artist ERC-2981 Royalty, 1.5% Treasury Safe)
/// - Physical NFC Confirmation Gate (C-06) via EIP-712 Attestation
/// - 14-Day Post-Expiry Refund Auto-Return (C-12)
contract ArthenticEscrow is AttestationVerifier {
    enum Status { None, Listed, Funded, Completed, Refunded, Disputed, Cancelled }

    struct Listing {
        uint256 tokenId;
        address seller;
        address buyer;
        address currency;       // address(0) for Native ETH, ERC-20 address for USDC
        uint256 price;
        uint64 expiry;          // Timestamp after which refund() is permitted
        Status status;
    }

    ArthenticNFT public immutable nft;
    address public treasurySafe;
    address public admin;

    // Listing ID => Listing Data
    uint256 public nextListingId = 1;
    mapping(uint256 => Listing) public listings;

    // Reentrancy guard
    uint8 private _locked = 1;

    // Protocol Constants (bps)
    uint16 public constant ARTIST_ROYALTY_BPS = 500;   // 5.0% (ADR-05)
    uint16 public constant PLATFORM_FEE_BPS   = 150;   // 1.5% (ADR-05)
    uint16 public constant TOTAL_BPS          = 10000;

    // Custom Errors
    error REENTRANCY();
    error INVALID_PRICE();
    error INVALID_STATUS();
    error NOT_SELLER();
    error NOT_BUYER();
    error EXPIRY_NOT_REACHED();
    error PAYMENT_FAILED();
    error TRANSFER_FAILED();
    error ETH_VALUE_MISMATCH();
    error ZERO_ADDRESS();

    // Events
    event ListingCreated(uint256 indexed listingId, uint256 indexed tokenId, address indexed seller, uint256 price, address currency, uint64 expiry);
    event ListingCancelled(uint256 indexed listingId);
    event EscrowFunded(uint256 indexed listingId, address indexed buyer, uint256 amount);
    event ClaimCompleted(
        uint256 indexed listingId,
        uint256 indexed tokenId,
        address indexed buyer,
        uint256 sellerNet,
        uint256 artistRoyalty,
        uint256 protocolFee
    );
    event EscrowRefunded(uint256 indexed listingId, address indexed buyer, uint256 amount);
    event EscrowDisputed(uint256 indexed listingId, string reasonURI);
    event DisputeResolved(uint256 indexed listingId, bool releasedToSeller);

    modifier nonReentrant() {
        if (_locked != 1) revert REENTRANCY();
        _locked = 2;
        _;
        _locked = 1;
    }

    constructor(address _nft, address _treasurySafe, address _admin)
        AttestationVerifier("ArthenticEscrow", "1")
    {
        if (_nft == address(0) || _treasurySafe == address(0) || _admin == address(0)) revert ZERO_ADDRESS();
        nft = ArthenticNFT(_nft);
        treasurySafe = _treasurySafe;
        admin = _admin;
    }

    function hasRole(bytes32 role, address account) public view override returns (bool) {
        return nft.hasRole(role, account);
    }

    /// @notice C-01: Seller deposits NFT into Escrow and lists artwork
    function createListing(
        uint256 tokenId,
        address currency,
        uint256 price,
        uint64 expiry
    ) external nonReentrant returns (uint256) {
        if (price == 0) revert INVALID_PRICE();
        if (expiry <= block.timestamp) revert INVALID_STATUS();

        uint256 listingId = nextListingId++;
        listings[listingId] = Listing({
            tokenId: tokenId,
            seller: msg.sender,
            buyer: address(0),
            currency: currency,
            price: price,
            expiry: expiry,
            status: Status.Listed
        });

        emit ListingCreated(listingId, tokenId, msg.sender, price, currency, expiry);

        // Transfer NFT from seller to Escrow contract
        nft.transferFrom(msg.sender, address(this), tokenId);

        return listingId;
    }

    /// @notice C-03*: Seller cancels active listing before buyer funds
    function cancelListing(uint256 listingId) external nonReentrant {
        Listing storage l = listings[listingId];
        if (l.status != Status.Listed) revert INVALID_STATUS();
        if (l.seller != msg.sender && msg.sender != admin) revert NOT_SELLER();

        l.status = Status.Cancelled;
        emit ListingCancelled(listingId);

        nft.transferFrom(address(this), l.seller, l.tokenId);
    }

    /// @notice C-04: Buyer deposits ETH or USDC into Escrow
    function deposit(uint256 listingId) external payable nonReentrant {
        Listing storage l = listings[listingId];
        if (l.status != Status.Listed) revert INVALID_STATUS();

        l.buyer = msg.sender;
        l.status = Status.Funded;

        if (l.currency == address(0)) {
            // Native Base ETH
            if (msg.value != l.price) revert ETH_VALUE_MISMATCH();
        } else {
            // ERC-20 USDC
            if (msg.value != 0) revert ETH_VALUE_MISMATCH();
            bool success = IERC20(l.currency).transferFrom(msg.sender, address(this), l.price);
            if (!success) revert PAYMENT_FAILED();
        }

        emit EscrowFunded(listingId, msg.sender, l.price);
    }

    /// @notice C-06: Buyer taps physical NFC chip on arrival, submitting Protocol Node attestation
    /// Executes the ADR-05 3-Way Atomic Split: 93.5% Seller, 5.0% Artist, 1.5% Treasury Safe
    function claim(
        uint256 listingId,
        Attestation calldata a,
        bytes calldata sig
    ) external nonReentrant {
        Listing storage l = listings[listingId];
        if (l.status != Status.Funded) revert INVALID_STATUS();
        if (msg.sender != l.buyer && msg.sender != admin) revert NOT_BUYER();
        if (a.tokenId != l.tokenId) revert INVALID_STATUS();

        // Verify Protocol Node Attestation
        _verifyAttestation(a, sig, false);

        l.status = Status.Completed;

        // Calculate ADR-05 Split
        (address artist, uint256 royalty) = nft.royaltyInfo(l.tokenId, l.price);
        if (artist == address(0)) artist = nft.tokenArtist(l.tokenId);

        uint256 artistRoyalty = royalty > 0 ? royalty : (l.price * ARTIST_ROYALTY_BPS) / TOTAL_BPS; // 5.0%
        uint256 protocolFee   = (l.price * PLATFORM_FEE_BPS) / TOTAL_BPS;                            // 1.5%
        uint256 sellerNet     = l.price - artistRoyalty - protocolFee;                               // 93.5%

        emit ClaimCompleted(listingId, l.tokenId, l.buyer, sellerNet, artistRoyalty, protocolFee);

        // Transfer funds
        if (l.currency == address(0)) {
            (bool s1, ) = l.seller.call{value: sellerNet}("");
            (bool s2, ) = artist.call{value: artistRoyalty}("");
            (bool s3, ) = treasurySafe.call{value: protocolFee}("");
            if (!s1 || !s2 || !s3) revert PAYMENT_FAILED();
        } else {
            bool s1 = IERC20(l.currency).transfer(l.seller, sellerNet);
            bool s2 = IERC20(l.currency).transfer(artist, artistRoyalty);
            bool s3 = IERC20(l.currency).transfer(treasurySafe, protocolFee);
            if (!s1 || !s2 || !s3) revert PAYMENT_FAILED();
        }

        // Release NFT to Buyer
        nft.transferFrom(address(this), l.buyer, l.tokenId);
    }

    /// @notice C-12: Auto-Refund if physical delivery not confirmed before expiry
    function refund(uint256 listingId) external nonReentrant {
        Listing storage l = listings[listingId];
        if (l.status != Status.Funded) revert INVALID_STATUS();
        if (block.timestamp <= l.expiry) revert EXPIRY_NOT_REACHED();

        l.status = Status.Refunded;
        emit EscrowRefunded(listingId, l.buyer, l.price);

        // 100% refund to Buyer
        if (l.currency == address(0)) {
            (bool ok, ) = l.buyer.call{value: l.price}("");
            if (!ok) revert PAYMENT_FAILED();
        } else {
            bool ok = IERC20(l.currency).transfer(l.buyer, l.price);
            if (!ok) revert PAYMENT_FAILED();
        }

        // Return NFT to Seller
        nft.transferFrom(address(this), l.seller, l.tokenId);
    }

    /// @notice C-10: Buyer or Seller freezes escrow due to transit dispute or surface mismatch
    function dispute(uint256 listingId, string calldata reasonURI) external nonReentrant {
        Listing storage l = listings[listingId];
        if (l.status != Status.Funded) revert INVALID_STATUS();
        if (msg.sender != l.buyer && msg.sender != l.seller && msg.sender != admin) revert ACCESS_DENIED();

        l.status = Status.Disputed;
        emit EscrowDisputed(listingId, reasonURI);
    }

    /// @notice C-11: Arbitrator Council settles dispute
    function resolveDispute(uint256 listingId, bool releaseToSeller) external nonReentrant {
        if (msg.sender != admin) revert ACCESS_DENIED();
        Listing storage l = listings[listingId];
        if (l.status != Status.Disputed) revert INVALID_STATUS();

        emit DisputeResolved(listingId, releaseToSeller);

        if (releaseToSeller) {
            l.status = Status.Completed;
            (address artist, uint256 royalty) = nft.royaltyInfo(l.tokenId, l.price);
            if (artist == address(0)) artist = nft.tokenArtist(l.tokenId);
            uint256 artistRoyalty = royalty > 0 ? royalty : (l.price * ARTIST_ROYALTY_BPS) / TOTAL_BPS;
            uint256 protocolFee   = (l.price * PLATFORM_FEE_BPS) / TOTAL_BPS;
            uint256 sellerNet     = l.price - artistRoyalty - protocolFee;

            if (l.currency == address(0)) {
                (bool s1, ) = l.seller.call{value: sellerNet}("");
                (bool s2, ) = artist.call{value: artistRoyalty}("");
                (bool s3, ) = treasurySafe.call{value: protocolFee}("");
                if (!s1 || !s2 || !s3) revert PAYMENT_FAILED();
            } else {
                if (!IERC20(l.currency).transfer(l.seller, sellerNet)) revert PAYMENT_FAILED();
                if (!IERC20(l.currency).transfer(artist, artistRoyalty)) revert PAYMENT_FAILED();
                if (!IERC20(l.currency).transfer(treasurySafe, protocolFee)) revert PAYMENT_FAILED();
            }
            nft.transferFrom(address(this), l.buyer, l.tokenId);
        } else {
            l.status = Status.Refunded;
            if (l.currency == address(0)) {
                (bool ok, ) = l.buyer.call{value: l.price}("");
                if (!ok) revert PAYMENT_FAILED();
            } else {
                if (!IERC20(l.currency).transfer(l.buyer, l.price)) revert PAYMENT_FAILED();
            }
            nft.transferFrom(address(this), l.seller, l.tokenId);
        }
    }
}

