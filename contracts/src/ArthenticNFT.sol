// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Roles} from "./Roles.sol";
import {AttestationVerifier} from "./AttestationVerifier.sol";

/// @title ArthenticNFT
/// @notice Base L2 Core ERC-721 + ERC-2981 Artwork Identity contract.
/// Enforces physical chip binding (SC-CHIP-01), immutable genesis vector hash (SC-GEN-01),
/// Artist EIP-712 co-signature (ADR-02 / B-07), Owner restoration consent (ADR-03 / E-07*),
/// and 3-of-3 multi-approval chip replacement (F-05).
contract ArthenticNFT is AttestationVerifier {
    // --- ERC-721 Metadata ---
    string public name = "Arthentic Physical Artwork";
    string public symbol = "ARTH";

    // --- Access Control Roles ---
    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;
    mapping(bytes32 => mapping(address => bool)) private _roles;

    // --- State Invariants ---
    mapping(bytes32 => bool) public chipBound;              // SC-CHIP-01: One chip cannot be bound to two tokens
    mapping(uint256 => bytes32) public genesisHash;         // SC-GEN-01: Immutable once set
    mapping(uint256 => bytes32) public activeChip;          // Currently bound physical chipIdHash
    mapping(uint256 => bool) public destroyed;              // Flagged permanently destroyed
    mapping(uint256 => address) public tokenArtist;         // Original accredited artist
    mapping(uint256 => string) private _tokenURIs;
    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(address => mapping(address => bool)) private _operatorApprovals;

    // ERC-2981 Royalty Storage (500 bps = 5.0%)
    uint96 public constant DEFAULT_ROYALTY_BPS = 500;
    mapping(uint256 => address) public royaltyRecipient;
    mapping(uint256 => uint96) public royaltyBps;

    // Pausability
    bool public paused;
    uint256 public nextTokenId = 1;

    // EIP-712 TypeHashes
    bytes32 public constant GENESIS_DOSSIER_TYPEHASH = keccak256(
        "GenesisDossier(address artist,bytes32 genesisVectorHash,bytes32 chipIdHash,bytes32 metadataHash)"
    );
    bytes32 public constant OWNER_CONSENT_TYPEHASH = keccak256(
        "OwnerConsent(uint256 tokenId,bytes32 newVectorHash,bytes32 noteHash,uint256 nonce)"
    );
    bytes32 public constant CHIP_REPLACEMENT_TYPEHASH = keccak256(
        "ChipReplacementApproval(uint256 tokenId,bytes32 oldChipIdHash,bytes32 newChipIdHash,bytes32 opticalDigest)"
    );

    // Custom Errors
    error GENESIS_IMMUTABLE();
    error CHIP_ALREADY_BOUND();
    error ARTIST_ROLE_REQUIRED();
    error ARTIST_COSIGN_INVALID();
    error OWNER_CONSENT_INVALID();
    error CHIP_APPROVAL_INVALID(uint8 index);
    error ARTWORK_DESTROYED();
    error CONTRACT_PAUSED();
    error NOT_OWNER_OR_APPROVED();
    error INVALID_TOKEN();

    // Events
    event GenesisRegistered(
        uint256 indexed tokenId,
        address indexed artist,
        address indexed verifier,
        bytes32 genesisHash,
        bytes32 chipIdHash,
        string metadataURI
    );
    event ConditionUpdated(
        uint256 indexed tokenId,
        bytes32 newVectorHash,
        address indexed conservator,
        string noteURI,
        uint256 timestamp
    );
    event ChipReplaced(
        uint256 indexed tokenId,
        bytes32 oldChipIdHash,
        bytes32 newChipIdHash,
        address indexed verifier,
        uint256 timestamp
    );
    event VerificationRecorded(
        uint256 indexed tokenId,
        uint16 similarityBps,
        address indexed recorder,
        uint256 timestamp
    );
    event ArtworkDestroyed(uint256 indexed tokenId, string proofURI, uint256 timestamp);
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);
    event Paused(address account);
    event Unpaused(address account);
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    modifier whenNotPaused() {
        if (paused) revert CONTRACT_PAUSED();
        _;
    }

    modifier onlyRole(bytes32 role) {
        if (!_roles[role][msg.sender] && !_roles[DEFAULT_ADMIN_ROLE][msg.sender]) {
            revert ACCESS_DENIED();
        }
        _;
    }

    constructor(address initialAdmin, address protocolNode)
        AttestationVerifier("ArthenticNFT", "1")
    {
        _roles[DEFAULT_ADMIN_ROLE][initialAdmin] = true;
        _roles[Roles.PROTOCOL_NODE_ROLE][protocolNode] = true;
        emit RoleGranted(DEFAULT_ADMIN_ROLE, initialAdmin, msg.sender);
        emit RoleGranted(Roles.PROTOCOL_NODE_ROLE, protocolNode, msg.sender);
    }

    // --- AccessControl Implementation ---
    function hasRole(bytes32 role, address account) public view override returns (bool) {
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

    // --- Circuit Breaker (J-01) ---
    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        paused = false;
        emit Unpaused(msg.sender);
    }

    // --- UC-B: Genesis Mint with Mandatory Artist Co-Sign (B-08 / ADR-02) ---
    function genesisMint(
        address artist,
        bytes32 genesisVectorHash,
        bytes32 chipIdHash,
        string calldata metadataURI,
        bytes calldata artistSig
    ) external whenNotPaused onlyRole(Roles.VERIFIER_ROLE) returns (uint256) {
        if (!hasRole(Roles.ARTIST_ROLE, artist)) revert ARTIST_ROLE_REQUIRED();
        if (chipBound[chipIdHash]) revert CHIP_ALREADY_BOUND();
        if (genesisVectorHash == bytes32(0)) revert INVALID_TOKEN();

        // ADR-02: Verify Artist EIP-712 Co-Sign on-chain before minting
        bytes32 dossierDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                DOMAIN_SEPARATOR,
                keccak256(
                    abi.encode(
                        GENESIS_DOSSIER_TYPEHASH,
                        artist,
                        genesisVectorHash,
                        chipIdHash,
                        keccak256(bytes(metadataURI))
                    )
                )
            )
        );
        address recoveredArtist = _recoverSigner(dossierDigest, artistSig);
        if (recoveredArtist != artist) revert ARTIST_COSIGN_INVALID();

        uint256 tokenId = nextTokenId++;

        // SC-GEN-01 & SC-CHIP-01 binding
        genesisHash[tokenId] = genesisVectorHash;
        activeChip[tokenId] = chipIdHash;
        chipBound[chipIdHash] = true;
        tokenArtist[tokenId] = artist;
        _tokenURIs[tokenId] = metadataURI;

        // Set ERC-2981 royalty: 5.0% to Artist
        royaltyRecipient[tokenId] = artist;
        royaltyBps[tokenId] = DEFAULT_ROYALTY_BPS;

        emit GenesisRegistered(tokenId, artist, msg.sender, genesisVectorHash, chipIdHash, metadataURI);

        _mint(artist, tokenId);

        return tokenId;
    }

    // --- UC-D: On-Chain Verification Recording (D-04) ---
    function recordVerification(Attestation calldata a, bytes calldata sig) external whenNotPaused {
        if (destroyed[a.tokenId]) revert ARTWORK_DESTROYED();
        _verifyAttestation(a, sig, false);
        emit VerificationRecorded(a.tokenId, a.similarityBps, msg.sender, block.timestamp);
    }

    // --- UC-E: Post-Restoration Condition Update (E-03 / ADR-03) ---
    function updateCondition(
        uint256 tokenId,
        bytes32 newVectorHash,
        string calldata noteURI,
        bytes calldata ownerConsentSig
    ) external whenNotPaused onlyRole(Roles.CONSERVATOR_ROLE) {
        if (destroyed[tokenId]) revert ARTWORK_DESTROYED();
        if (newVectorHash == bytes32(0)) revert INVALID_TOKEN();
        address owner = ownerOf(tokenId);

        // ADR-03 (E-07*): Enforce Owner Consent EIP-712 Signature
        bytes32 consentDigest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                DOMAIN_SEPARATOR,
                keccak256(
                    abi.encode(
                        OWNER_CONSENT_TYPEHASH,
                        tokenId,
                        newVectorHash,
                        keccak256(bytes(noteURI)),
                        tokenId
                    )
                )
            )
        );
        address recoveredOwner = _recoverSigner(consentDigest, ownerConsentSig);
        if (recoveredOwner != owner) revert OWNER_CONSENT_INVALID();

        // Note: genesisHash[tokenId] is left strictly unchanged!
        emit ConditionUpdated(tokenId, newVectorHash, msg.sender, noteURI, block.timestamp);
    }

    // --- UC-F: 3-of-3 Chip Replacement (F-05) ---
    function replaceChip(
        uint256 tokenId,
        bytes32 newChipIdHash,
        Attestation calldata optical,
        bytes calldata nodeSig,
        bytes[3] calldata approvals
    ) external whenNotPaused onlyRole(Roles.VERIFIER_ROLE) {
        if (destroyed[tokenId]) revert ARTWORK_DESTROYED();
        if (chipBound[newChipIdHash]) revert CHIP_ALREADY_BOUND();
        bytes32 oldChip = activeChip[tokenId];

        // 1. Enforce optical gate >= 8800 bps
        _verifyAttestation(optical, nodeSig, true);

        // 2. Compute Replacement Digest
        bytes32 digest = keccak256(
            abi.encodePacked(
                "\x19\x01",
                DOMAIN_SEPARATOR,
                keccak256(
                    abi.encode(
                        CHIP_REPLACEMENT_TYPEHASH,
                        tokenId,
                        oldChip,
                        newChipIdHash,
                        optical.sunDigest
                    )
                )
            )
        );

        // 3. Verify Approval 1/3: Current Owner (Collector)
        if (_recoverSigner(digest, approvals[0]) != ownerOf(tokenId)) revert CHIP_APPROVAL_INVALID(0);

        // 4. Verify Approval 2/3: Original Artist
        address artist = tokenArtist[tokenId];
        if (_recoverSigner(digest, approvals[1]) != artist) revert CHIP_APPROVAL_INVALID(1);

        // 5. Verify Approval 3/3: Verifier Gallery
        if (_recoverSigner(digest, approvals[2]) != msg.sender) revert CHIP_APPROVAL_INVALID(2);

        // 6. Unbind old chip, bind new chip
        chipBound[oldChip] = false;
        chipBound[newChipIdHash] = true;
        activeChip[tokenId] = newChipIdHash;

        emit ChipReplaced(tokenId, oldChip, newChipIdHash, msg.sender, block.timestamp);
    }

    // --- Mark Destroyed ---
    function markDestroyed(uint256 tokenId, string calldata proofURI)
        external
        onlyRole(Roles.VERIFIER_ROLE)
    {
        if (_owners[tokenId] == address(0)) revert INVALID_TOKEN();
        destroyed[tokenId] = true;
        emit ArtworkDestroyed(tokenId, proofURI, block.timestamp);
    }

    // --- ERC-2981 Royalty Info ---
    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        external
        view
        returns (address receiver, uint256 royaltyAmount)
    {
        receiver = royaltyRecipient[tokenId];
        if (receiver == address(0)) receiver = tokenArtist[tokenId];
        uint96 bps = royaltyBps[tokenId] > 0 ? royaltyBps[tokenId] : DEFAULT_ROYALTY_BPS;
        royaltyAmount = (salePrice * bps) / 10000;
    }

    // --- Minimal ERC-721 Core Implementation ---
    function ownerOf(uint256 tokenId) public view returns (address) {
        address owner = _owners[tokenId];
        if (owner == address(0)) revert INVALID_TOKEN();
        return owner;
    }

    function tokenURI(uint256 tokenId) public view returns (string memory) {
        if (_owners[tokenId] == address(0)) revert INVALID_TOKEN();
        return _tokenURIs[tokenId];
    }

    function balanceOf(address owner) public view returns (uint256) {
        return _balances[owner];
    }

    function transferFrom(address from, address to, uint256 tokenId) public whenNotPaused {
        if (destroyed[tokenId]) revert ARTWORK_DESTROYED();
        address owner = ownerOf(tokenId);
        if (from != owner) revert NOT_OWNER_OR_APPROVED();
        if (to == address(0)) revert INVALID_TOKEN();
        if (msg.sender != owner && msg.sender != _tokenApprovals[tokenId] && !_operatorApprovals[owner][msg.sender]) {
            revert NOT_OWNER_OR_APPROVED();
        }

        delete _tokenApprovals[tokenId];
        _balances[from] -= 1;
        _balances[to] += 1;
        _owners[tokenId] = to;

        emit Transfer(from, to, tokenId);
    }

    function approve(address to, uint256 tokenId) public whenNotPaused {
        address owner = ownerOf(tokenId);
        if (msg.sender != owner && !_operatorApprovals[owner][msg.sender]) revert NOT_OWNER_OR_APPROVED();
        _tokenApprovals[tokenId] = to;
        emit Approval(owner, to, tokenId);
    }

    function setApprovalForAll(address operator, bool approved) public whenNotPaused {
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function _mint(address to, uint256 tokenId) internal {
        _balances[to] += 1;
        _owners[tokenId] = to;
        emit Transfer(address(0), to, tokenId);
    }
}

