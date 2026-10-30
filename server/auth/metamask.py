import uuid
import secrets
from datetime import timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session as DBSession
from fastapi import HTTPException, status
from eth_account.messages import encode_defunct
from eth_account import Account

from server.config import settings
from server.storage import store
from server.db.models import (
    User,
    Device,
    Session,
    RefreshToken,
    AuthIdentity,
    WalletLink,
)
from server.auth.clock import get_current_time
from server.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from server.auth.service import create_audit_entry, get_user_roles, normalize_role


# Supported role-specific MetaMask actions mapped to UML Feature IDs
ROLE_METAMASK_ACTIONS: Dict[str, Dict[str, Any]] = {
    "B-07": {
        "name": "Genesis Co-Signature (EIP-712)",
        "required_role": "Artist",
        "contract": "ArthenticNFT (Off-chain EIP-712 -> B-08)",
        "gas_mode": "Gasless (EIP-712 Typed Data Signature)",
        "description": "Artist co-signs genesis dossier (title, genesisVectorHash, chipIdHash, 5% ERC-2981 royalty).",
    },
    "B-08": {
        "name": "genesisMint() via Safe Multisig",
        "required_role": "Gallery",
        "contract": "ArthenticNFT.genesisMint()",
        "gas_mode": "Safe Multisig / MetaMask EOA Signer",
        "description": "Gallery Verifier signs Safe multisig transaction to bind NFC chip and mint ERC-721 to Artist.",
    },
    "C-01": {
        "name": "Create Primary Listing",
        "required_role": "Artist",
        "contract": "ArthenticEscrow.createListing()",
        "gas_mode": "Sponsored (T2) or MetaMask Self-Pay (K-04)",
        "description": "Approves and transfers artwork NFT into ArthenticEscrow with price and expiry.",
    },
    "C-03": {
        "name": "Cancel Listing",
        "required_role": "Collector",
        "contract": "ArthenticEscrow.cancelListing()",
        "gas_mode": "MetaMask Self-Pay (Base L2)",
        "description": "Seller cancels an active Listed escrow before buyer deposit and reclaims NFT.",
    },
    "C-04": {
        "name": "Deposit to Escrow",
        "required_role": "Collector",
        "contract": "ArthenticEscrow.deposit()",
        "gas_mode": "MetaMask Value Tx (ETH / USDC) + Paymaster T1",
        "description": "Buyer locks purchase price in ArthenticEscrow while physical artwork is shipped.",
    },
    "C-06": {
        "name": "Tap Claim (Physical Arrival)",
        "required_role": "Collector",
        "contract": "ArthenticEscrow.claim()",
        "gas_mode": "Paymaster Sponsored (T1) or MetaMask Self-Pay",
        "description": "Buyer taps NTAG 424 DNA chip on arrival; submits Node EIP-712 attestation to release NFT & split 5% royalty.",
    },
    "C-10": {
        "name": "Create Resale Listing",
        "required_role": "Collector",
        "contract": "ArthenticEscrow.createListing()",
        "gas_mode": "Sponsored (T2) or MetaMask Self-Pay",
        "description": "Collector lists owned artwork for secondary sale after fresh L1/L2 verification.",
    },
    "C-12": {
        "name": "Verify Ownership Sync",
        "required_role": "Collector",
        "contract": "ArthenticNFT.ownerOf()",
        "gas_mode": "Read-Only RPC Check + MetaMask Address Match",
        "description": "Secondary Buyer verifies seller's MetaMask wallet matches on-chain ownerOf(tokenId).",
    },
    "D-04": {
        "name": "Record Verification On-Chain",
        "required_role": "Collector",
        "contract": "ArthenticNFT.recordVerification()",
        "gas_mode": "Paymaster Sponsored (T3) / K-04 Self-Pay Fallback",
        "description": "Anchors L1 NFC or L2 Optical verification attestation on Base L2.",
    },
    "E-03": {
        "name": "updateCondition() Post-Restoration",
        "required_role": "Conservator",
        "contract": "ArthenticNFT.updateCondition()",
        "gas_mode": "MetaMask EOA / Sponsored (T2)",
        "description": "Conservator records new surface vector hash and Arweave/IPFS restoration report URI while keeping genesisHash immutable.",
    },
    "E-07": {
        "name": "Owner Consent for Restoration (EIP-712)",
        "required_role": "Collector",
        "contract": "ArthenticApp / ArthenticNFT Consent",
        "gas_mode": "Gasless (EIP-712 Typed Data Signature)",
        "description": "Artwork owner signs EIP-712 consent approving Conservator's restoration report and new vector hash.",
    },
    "F-05": {
        "name": "Replace Damaged Chip (3-of-3 Approval)",
        "required_role": "Collector",
        "contract": "ArthenticNFT.replaceChip()",
        "gas_mode": "EIP-712 Multi-Party Approval (Collector, Artist, Verifier)",
        "description": "Signs EIP-712 approval to bind newChipIdHash after L2 optical verification >= 8800 bps.",
    },
    "A-06": {
        "name": "Grant Role via Safe Multisig",
        "required_role": "Admin",
        "contract": "ArthenticNFT.grantRole()",
        "gas_mode": "Safe Multisig (MetaMask Signer)",
        "description": "Protocol Admin grants ARTIST_ROLE, VERIFIER_ROLE, or CONSERVATOR_ROLE on-chain.",
    },
    "J-01": {
        "name": "Emergency Pause / Unpause",
        "required_role": "Admin",
        "contract": "ArthenticNFT.pause() / ArthenticEscrow.pause()",
        "gas_mode": "Safe Multisig (MetaMask Signer)",
        "description": "Protocol Admin triggers emergency circuit breaker across contracts during security incidents.",
    },
}


def normalize_eth_address(address: str) -> str:
    addr = address.strip().lower()
    if not addr.startswith("0x") or len(addr) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_WALLET_ADDRESS", "message": "Invalid Ethereum/Base wallet address format."}},
        )
    return addr


def generate_metamask_challenge(address: str, chain_id: int = 84532) -> Dict[str, Any]:
    norm_addr = normalize_eth_address(address)
    nonce = secrets.token_hex(16)
    now_iso = get_current_time().isoformat()
    message = (
        f"arthentic.io wants you to sign in with your Ethereum account:\n"
        f"{norm_addr}\n\n"
        f"Sign in to Arthentic Phygital Authentication Protocol on Base L2.\n\n"
        f"URI: https://arthentic.io\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {now_iso}"
    )
    store.challenges[norm_addr] = {
        "nonce": nonce,
        "message": message,
        "chain_id": chain_id,
        "issued_at": now_iso,
    }
    return {
        "address": norm_addr,
        "chain_id": chain_id,
        "nonce": nonce,
        "message": message,
        "wc_deep_link": f"metamask://wc?uri=wc:{nonce}@2?relay-protocol=irn&chainId=eip155:{chain_id}",
    }


def verify_metamask_signature(address: str, signature: str) -> Tuple[bool, str]:
    norm_addr = normalize_eth_address(address)
    challenge_data = store.challenges.get(norm_addr)
    if not challenge_data:
        return False, ""

    if isinstance(challenge_data, dict):
        expected_nonce = challenge_data.get("nonce", "")
        expected_message = challenge_data.get("message", "")
    elif isinstance(challenge_data, str):
        expected_nonce = challenge_data
        expected_message = f"Sign in to Arthentic\nAddress: {norm_addr}\nNonce: {expected_nonce}"
    else:
        return False, ""

    # Real ECDSA secp256k1 verification across SIWE message, legacy challenge, or raw nonce
    candidate_messages = [
        expected_message,
        f"Sign in to Arthentic\nAddress: {norm_addr}\nNonce: {expected_nonce}",
        expected_nonce,
    ]
    for msg in candidate_messages:
        if not msg:
            continue
        try:
            signable = encode_defunct(text=msg)
            recovered = Account.recover_message(signable, signature=signature).lower()
            if recovered == norm_addr:
                # Consume challenge nonce to prevent replay attacks
                store.challenges.pop(norm_addr, None)
                return True, expected_nonce
        except Exception:
            continue

    return False, expected_nonce


def get_user_wallets(db: DBSession, user_id: str) -> List[Dict[str, Any]]:
    links = (
        db.query(WalletLink)
        .filter(WalletLink.user_id == user_id)
        .order_by(WalletLink.is_primary.desc(), WalletLink.created_at.asc())
        .all()
    )
    return [
        {
            "id": w.id,
            "address": w.address,
            "chain_id": w.chain_id,
            "wallet_type": w.wallet_type,
            "label": w.label or ("MetaMask EOA" if w.wallet_type == "metamask" else w.wallet_type),
            "is_primary": w.is_primary,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in links
    ]


def authenticate_metamask(
    db: DBSession,
    address: str,
    signature: str,
    chain_id: int = 84532,
    wallet_type: str = "metamask",
    display_name: Optional[str] = None,
    install_id: Optional[str] = None,
    device_name: Optional[str] = None,
    platform: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    norm_addr = normalize_eth_address(address)
    is_valid, used_nonce = verify_metamask_signature(norm_addr, signature)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_METAMASK_SIGNATURE", "message": "MetaMask signature verification failed."}},
        )

    # Consume challenge nonce to prevent replay
    store.challenges.pop(norm_addr, None)
    now = get_current_time()

    # 1. Check if wallet is already linked in wallet_links
    wallet_link = (
        db.query(WalletLink)
        .filter(WalletLink.address == norm_addr, WalletLink.chain_id == chain_id)
        .first()
    )

    user: Optional[User] = None
    if wallet_link:
        user = db.query(User).filter(User.id == wallet_link.user_id).first()

    # 2. Fallback check in AuthIdentity(provider='metamask')
    if not user:
        identity = (
            db.query(AuthIdentity)
            .filter(AuthIdentity.provider == "metamask", AuthIdentity.provider_subject == norm_addr)
            .first()
        )
        if identity:
            user = db.query(User).filter(User.id == identity.user_id).first()

    if user:
        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "ACCOUNT_INACTIVE", "message": "Account is inactive or disabled."}},
            )
        user.last_login_at = now
        action = "AUTH_METAMASK_LOGIN"
    else:
        # Create new Web3 user account
        short_addr = f"{norm_addr[:6]}...{norm_addr[-4:]}"
        synthetic_email = f"{norm_addr}@metamask.arthentic.io"
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=synthetic_email,
            display_name=display_name or f"MetaMask ({short_addr})",
            password_hash=None,
            email_verified_at=now,
            status="active",
            created_at=now,
            last_login_at=now,
        )
        db.add(user)

        identity = AuthIdentity(
            id=str(uuid.uuid4()),
            user_id=user_id,
            provider="metamask",
            provider_subject=norm_addr,
            email_at_link=synthetic_email,
            created_at=now,
        )
        db.add(identity)
        action = "AUTH_METAMASK_SIGNUP"

    if not wallet_link:
        wallet_link = WalletLink(
            id=str(uuid.uuid4()),
            user_id=user.id,
            address=norm_addr,
            chain_id=chain_id,
            wallet_type=wallet_type,
            label="MetaMask Mobile (EOA)" if wallet_type == "metamask" else wallet_type,
            is_primary=True,
            created_at=now,
        )
        db.add(wallet_link)

    # Device registration
    device_obj = None
    if install_id:
        device_obj = (
            db.query(Device)
            .filter(Device.user_id == user.id, Device.install_id == install_id)
            .first()
        )
        if not device_obj:
            device_obj = Device(
                id=str(uuid.uuid4()),
                user_id=user.id,
                install_id=install_id,
                name=device_name or "MetaMask Mobile Device",
                platform=platform or "ios",
                created_at=now,
                last_seen_at=now,
            )
            db.add(device_obj)
        else:
            device_obj.last_seen_at = now

    # Create session & rotating refresh token
    session_id = str(uuid.uuid4())
    abs_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session_obj = Session(
        id=session_id,
        user_id=user.id,
        device_id=device_obj.id if device_obj else None,
        absolute_expires_at=abs_expires,
        created_at=now,
    )
    db.add(session_obj)

    raw_refresh = generate_refresh_token()
    family_id = str(uuid.uuid4())
    refresh_obj = RefreshToken(
        id=str(uuid.uuid4()),
        session_id=session_id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=family_id,
        expires_at=abs_expires,
        created_at=now,
    )
    db.add(refresh_obj)

    create_audit_entry(
        db,
        action=action,
        actor_user_id=user.id,
        target_type="wallet",
        target_id=wallet_link.id,
        ip=ip,
        device_id=device_obj.id if device_obj else None,
        meta={"address": norm_addr, "chain_id": chain_id, "wallet_type": wallet_type, "nonce": used_nonce},
    )

    db.commit()

    roles = get_user_roles(db, user.id)
    access_token = create_access_token(user_id=user.id, session_id=session_id, roles=roles)
    wallets = get_user_wallets(db, user.id)

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "roles": roles,
            "wallet_address": norm_addr,
            "wallets": wallets,
        },
    }


def link_metamask_wallet(
    db: DBSession,
    current_user: User,
    address: str,
    signature: str,
    chain_id: int = 84532,
    wallet_type: str = "metamask",
    label: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    norm_addr = normalize_eth_address(address)
    is_valid, used_nonce = verify_metamask_signature(norm_addr, signature)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_METAMASK_SIGNATURE", "message": "MetaMask signature verification failed."}},
        )

    store.challenges.pop(norm_addr, None)
    now = get_current_time()

    existing = (
        db.query(WalletLink)
        .filter(WalletLink.address == norm_addr, WalletLink.chain_id == chain_id)
        .first()
    )
    if existing:
        if existing.user_id == current_user.id:
            return {
                "status": "already_linked",
                "wallet": {
                    "id": existing.id,
                    "address": existing.address,
                    "chain_id": existing.chain_id,
                    "wallet_type": existing.wallet_type,
                    "label": existing.label,
                    "is_primary": existing.is_primary,
                },
                "wallets": get_user_wallets(db, current_user.id),
            }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "WALLET_ALREADY_LINKED", "message": "This MetaMask address is already linked to another account."}},
        )

    # Check if user has any primary wallet yet
    has_primary = (
        db.query(WalletLink)
        .filter(WalletLink.user_id == current_user.id, WalletLink.is_primary.is_(True))
        .first()
        is not None
    )

    wallet_link = WalletLink(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        address=norm_addr,
        chain_id=chain_id,
        wallet_type=wallet_type,
        label=label or ("MetaMask Mobile (EOA)" if wallet_type == "metamask" else wallet_type),
        is_primary=not has_primary,
        created_at=now,
    )
    db.add(wallet_link)

    # Also ensure AuthIdentity exists for direct MetaMask sign-in later
    existing_identity = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.provider == "metamask", AuthIdentity.provider_subject == norm_addr)
        .first()
    )
    if not existing_identity:
        db.add(
            AuthIdentity(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                provider="metamask",
                provider_subject=norm_addr,
                email_at_link=current_user.email,
                created_at=now,
            )
        )

    create_audit_entry(
        db,
        action="AUTH_METAMASK_LINKED",
        actor_user_id=current_user.id,
        target_type="wallet",
        target_id=wallet_link.id,
        ip=ip,
        meta={"address": norm_addr, "chain_id": chain_id, "wallet_type": wallet_type, "nonce": used_nonce},
    )
    db.commit()

    return {
        "status": "linked",
        "wallet": {
            "id": wallet_link.id,
            "address": wallet_link.address,
            "chain_id": wallet_link.chain_id,
            "wallet_type": wallet_link.wallet_type,
            "label": wallet_link.label,
            "is_primary": wallet_link.is_primary,
        },
        "wallets": get_user_wallets(db, current_user.id),
    }


def execute_metamask_role_action(
    db: DBSession,
    current_user: User,
    action_code: str,
    address: str,
    signature: str,
    token_id: str = "101",
    payload: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    code = action_code.strip().upper()
    if code not in ROLE_METAMASK_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "UNKNOWN_ACTION_CODE", "message": f"Unsupported UML action code '{action_code}'."}},
        )

    spec = ROLE_METAMASK_ACTIONS[code]
    required_role = spec["required_role"]
    user_roles = get_user_roles(db, current_user.id)

    # Verify the user holds the required role (Collector is held by all registered users)
    if required_role not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "ROLE_REQUIRED_FOR_METAMASK_ACTION",
                    "message": f"Action {code} ({spec['name']}) requires role '{required_role}', but active user holds {user_roles}.",
                }
            },
        )

    norm_addr = normalize_eth_address(address)
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "A valid MetaMask signature is required."}},
        )

    # Genuine cryptographic signature verification over the canonical action message
    action_msg = f"Arthentic Action Authorization\nAction: {code}\nTarget: {token_id}\nActor: {norm_addr}"
    try:
        signable = encode_defunct(text=action_msg)
        recovered = Account.recover_message(signable, signature=signature).lower()
        if recovered != norm_addr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "INVALID_SIGNATURE", "message": "MetaMask role action signature mismatch."}},
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "Malformed role action signature."}},
        )

    tx_hash = "0x" + secrets.token_hex(32)
    now = get_current_time()

    # Record provenance event for artwork-related actions
    store.add_provenance_event(
        token_id=token_id,
        event_type=f"METAMASK_{code.replace('-', '_')}",
        actor=norm_addr,
        role=required_role,
        details=f"{spec['name']} signed via MetaMask ({spec['contract']})",
    )

    create_audit_entry(
        db,
        action=f"METAMASK_ACTION_{code}",
        actor_user_id=current_user.id,
        target_type="artwork",
        target_id=token_id,
        ip=ip,
        meta={
            "action_code": code,
            "action_name": spec["name"],
            "role": required_role,
            "wallet_address": norm_addr,
            "contract": spec["contract"],
            "tx_hash": tx_hash,
            "payload": payload or {},
        },
    )
    db.commit()

    return {
        "status": "CONFIRMED",
        "action_code": code,
        "action_name": spec["name"],
        "role": required_role,
        "contract": spec["contract"],
        "gas_mode": spec["gas_mode"],
        "wallet_address": norm_addr,
        "token_id": token_id,
        "tx_hash": tx_hash,
        "timestamp": now.isoformat(),
    }
