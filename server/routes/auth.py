import uuid
import secrets
from fastapi import APIRouter, HTTPException, Header, Depends, Request
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Tuple, Dict, Any
from eth_account.messages import encode_defunct
from eth_account import Account
from sqlalchemy.orm import Session as DBSession

from server.storage import store
from server.db.database import get_db
from server.db.models import User, Session
from server.auth.service import (
    signup_user,
    login_user,
    refresh_tokens,
    logout_session,
    get_user_roles,
    list_user_sessions,
    revoke_user_session,
    change_user_password,
    request_password_reset,
    confirm_password_reset,
    request_email_verification,
    confirm_email_verification,
    delete_user_account,
    get_user_audit_log,
)
from server.auth.oauth import authenticate_oauth, link_oauth_identity
from server.auth.metamask import (
    generate_metamask_challenge,
    authenticate_metamask,
    link_metamask_wallet,
    get_user_wallets,
    execute_metamask_role_action,
    ROLE_METAMASK_ACTIONS,
)
from server.auth.dependencies import get_current_user_and_session

router = APIRouter(tags=["auth"])

# --- Request / Response Models ---

class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None
    install_id: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    install_id: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None

class RefreshRequest(BaseModel):
    refresh_token: str

class OAuthLoginRequest(BaseModel):
    id_token: str
    install_id: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None

class OAuthLinkRequest(BaseModel):
    provider: str
    id_token: str

class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class VerifyEmailConfirmRequest(BaseModel):
    token: str

class LockBypassReportRequest(BaseModel):
    details: Optional[str] = "Device local authentication anomaly"
    metadata: Optional[Dict[str, Any]] = None

class UserProfileResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    roles: List[str] = []
    wallet_address: Optional[str] = None
    wallets: List[Dict[str, Any]] = []

class MetaMaskChallengeRequest(BaseModel):
    address: str
    chain_id: int = 84532

class MetaMaskLoginRequest(BaseModel):
    address: str
    signature: str
    chain_id: int = 84532
    wallet_type: str = "metamask"
    display_name: Optional[str] = None
    install_id: Optional[str] = None
    device_name: Optional[str] = None
    platform: Optional[str] = None

class MetaMaskLinkRequest(BaseModel):
    address: str
    signature: str
    chain_id: int = 84532
    wallet_type: str = "metamask"
    label: Optional[str] = None

class MetaMaskRoleActionRequest(BaseModel):
    action_code: str
    address: str
    signature: str
    token_id: str = "101"
    payload: Optional[Dict[str, Any]] = None

class TokenAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Optional[UserProfileResponse] = None

class ChallengeRequest(BaseModel):
    address: str

class ChallengeResponse(BaseModel):
    nonce: str
    message: str

class VerifyRequest(BaseModel):
    address: str
    signature: str

class VerifyResponse(BaseModel):
    session: str
    roles: List[str]

# Helper to get client IP
def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

# --- Core Authentication Endpoints ---

@router.post("/auth/signup", response_model=TokenAuthResponse)
@router.post("/v1/auth/signup", response_model=TokenAuthResponse)
def signup(req: SignupRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return signup_user(
        db=db,
        email=req.email,
        password=req.password,
        display_name=req.display_name,
        install_id=req.install_id,
        device_name=req.device_name,
        platform=req.platform,
        ip=ip,
    )

@router.post("/auth/login", response_model=TokenAuthResponse)
@router.post("/v1/auth/login", response_model=TokenAuthResponse)
def login(req: LoginRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return login_user(
        db=db,
        email=req.email,
        password=req.password,
        install_id=req.install_id,
        device_name=req.device_name,
        platform=req.platform,
        ip=ip,
    )

@router.post("/auth/google", response_model=TokenAuthResponse)
@router.post("/v1/auth/google", response_model=TokenAuthResponse)
def login_google(req: OAuthLoginRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return authenticate_oauth(
        db=db,
        provider="google",
        id_token=req.id_token,
        install_id=req.install_id,
        device_name=req.device_name,
        platform=req.platform,
        ip=ip,
    )

@router.post("/auth/apple", response_model=TokenAuthResponse)
@router.post("/v1/auth/apple", response_model=TokenAuthResponse)
def login_apple(req: OAuthLoginRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return authenticate_oauth(
        db=db,
        provider="apple",
        id_token=req.id_token,
        install_id=req.install_id,
        device_name=req.device_name,
        platform=req.platform,
        ip=ip,
    )

@router.post("/auth/link")
@router.post("/v1/auth/link")
def link_account(
    req: OAuthLinkRequest,
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    return link_oauth_identity(
        db=db,
        current_user=user,
        provider=req.provider.lower(),
        id_token=req.id_token,
        ip=ip,
    )

@router.post("/auth/refresh", response_model=TokenAuthResponse)
@router.post("/v1/auth/refresh", response_model=TokenAuthResponse)
def refresh(req: RefreshRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return refresh_tokens(
        db=db,
        raw_refresh_token=req.refresh_token,
        ip=ip,
    )

@router.post("/auth/logout")
@router.post("/v1/auth/logout")
def logout(
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, session = auth_pair
    ip = get_client_ip(request)
    return logout_session(db=db, session_id=session.id, user_id=user.id, ip=ip)

@router.get("/auth/me", response_model=UserProfileResponse)
@router.get("/v1/auth/me", response_model=UserProfileResponse)
def get_me(
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    roles = get_user_roles(db, user.id)
    wallets = get_user_wallets(db, user.id)
    primary_addr = wallets[0]["address"] if wallets else None
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        roles=roles,
        wallet_address=primary_addr,
        wallets=wallets,
    )

# --- Sessions & Devices Management ---

@router.get("/auth/sessions")
@router.get("/v1/auth/sessions")
def get_sessions(
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, session = auth_pair
    sessions = list_user_sessions(db, user.id, current_session_id=session.id)
    return {"sessions": sessions}

@router.post("/auth/sessions/{session_id}/revoke")
@router.post("/v1/auth/sessions/{session_id}/revoke")
def revoke_session(
    session_id: str,
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    return revoke_user_session(db, user.id, session_id, ip=ip)

# --- Password Management ---

@router.post("/auth/password/change")
@router.post("/v1/auth/password/change")
@router.post("/auth/change-password")
@router.post("/v1/auth/change-password")
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, session = auth_pair
    ip = get_client_ip(request)
    return change_user_password(
        db=db,
        user_id=user.id,
        new_password=req.new_password,
        current_password=req.current_password,
        current_session_id=session.id,
        ip=ip,
    )

@router.post("/auth/password/forgot")
@router.post("/v1/auth/password/forgot")
def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    ip = get_client_ip(request)
    raw_token = request_password_reset(db, req.email, ip=ip)
    resp = {
        "status": "ok",
        "message": "If this email is registered, a password reset link has been sent.",
    }
    if raw_token:
        resp["reset_token"] = raw_token
    return resp

@router.post("/auth/password/reset")
@router.post("/v1/auth/password/reset")
def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    ip = get_client_ip(request)
    return confirm_password_reset(db, req.token, req.new_password, ip=ip)

# --- Email Verification ---

@router.post("/auth/verify-email/request")
@router.post("/v1/auth/verify-email/request")
def request_email_verify(
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    raw_token = request_email_verification(db, user.id, ip=ip)
    return {
        "status": "ok",
        "message": "Verification link has been sent.",
        "verify_token": raw_token,
    }

@router.post("/auth/verify-email/confirm")
@router.post("/v1/auth/verify-email/confirm")
def confirm_email_verify(
    req: VerifyEmailConfirmRequest,
    request: Request,
    db: DBSession = Depends(get_db),
):
    ip = get_client_ip(request)
    return confirm_email_verification(db, req.token, ip=ip)

# --- Account Deletion (Apple App Store Guideline 5.1.1(v)) ---

@router.delete("/auth/account")
@router.delete("/v1/auth/account")
def delete_account(
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    return delete_user_account(db, user.id, ip=ip)

# --- Security Audit View ---

@router.get("/auth/audit-log")
@router.get("/v1/auth/audit-log")
def get_user_security_events(
    limit: int = 50,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    events = get_user_audit_log(db, user.id, limit=limit)
    return {"events": events}

# --- Milestone 7 Monitoring & Lock Anomaly Reporting ---

@router.post("/auth/lock-bypass-report")
@router.post("/v1/auth/lock-bypass-report")
def report_lock_bypass(req: LockBypassReportRequest, request: Request):
    """
    Client telemetry reporting potential local auth/biometric bypass or tamper anomaly.
    """
    from server.auth.monitoring import monitoring
    ip = get_client_ip(request)
    monitoring.record_lock_bypass(details=req.details, client_ip=ip)
    return {"status": "ok", "message": "Anomaly report recorded"}

# --- MetaMask Wallet Integration (SIWE Challenge, Login, Link & Role Flows) ---

@router.post("/auth/metamask/challenge")
@router.post("/v1/auth/metamask/challenge")
def metamask_challenge(req: MetaMaskChallengeRequest):
    return generate_metamask_challenge(address=req.address, chain_id=req.chain_id)

@router.post("/auth/metamask/login", response_model=TokenAuthResponse)
@router.post("/v1/auth/metamask/login", response_model=TokenAuthResponse)
def metamask_login(req: MetaMaskLoginRequest, request: Request, db: DBSession = Depends(get_db)):
    ip = get_client_ip(request)
    return authenticate_metamask(
        db=db,
        address=req.address,
        signature=req.signature,
        chain_id=req.chain_id,
        wallet_type=req.wallet_type,
        display_name=req.display_name,
        install_id=req.install_id,
        device_name=req.device_name,
        platform=req.platform,
        ip=ip,
    )

@router.post("/auth/metamask/link")
@router.post("/v1/auth/metamask/link")
def metamask_link(
    req: MetaMaskLinkRequest,
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    return link_metamask_wallet(
        db=db,
        current_user=user,
        address=req.address,
        signature=req.signature,
        chain_id=req.chain_id,
        wallet_type=req.wallet_type,
        label=req.label,
        ip=ip,
    )

@router.get("/auth/wallets")
@router.get("/v1/auth/wallets")
def list_linked_wallets(
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    return {"wallets": get_user_wallets(db, user.id)}

@router.get("/auth/metamask/role-actions")
@router.get("/v1/auth/metamask/role-actions")
def list_metamask_role_actions():
    return {"actions": ROLE_METAMASK_ACTIONS}

@router.post("/auth/metamask/role-action")
@router.post("/v1/auth/metamask/role-action")
def run_metamask_role_action(
    req: MetaMaskRoleActionRequest,
    request: Request,
    auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
    db: DBSession = Depends(get_db),
):
    user, _ = auth_pair
    ip = get_client_ip(request)
    return execute_metamask_role_action(
        db=db,
        current_user=user,
        action_code=req.action_code,
        address=req.address,
        signature=req.signature,
        token_id=req.token_id,
        payload=req.payload,
        ip=ip,
    )

# --- Existing Web3 / Mock Endpoints for Backwards Compatibility ---

@router.post("/v1/auth/challenge", response_model=ChallengeResponse)
def get_challenge(req: ChallengeRequest):
    address = req.address.lower()
    nonce = secrets.token_hex(16)
    store.challenges[address] = nonce
    message = f"Sign in to Arthentic\nAddress: {address}\nNonce: {nonce}"
    return ChallengeResponse(nonce=nonce, message=message)

@router.post("/v1/auth/verify", response_model=VerifyResponse)
def verify_signature(req: VerifyRequest):
    address = req.address.lower()
    challenge_entry = store.challenges.get(address)
    if not challenge_entry:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "No active challenge found for address"}},
        )

    if isinstance(challenge_entry, dict):
        expected_nonce = challenge_entry.get("nonce", "")
        expected_message = challenge_entry.get("message", "")
    elif isinstance(challenge_entry, str):
        expected_nonce = challenge_entry
        expected_message = f"Sign in to Arthentic\nAddress: {address}\nNonce: {expected_nonce}"
    else:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "Invalid challenge state"}},
        )

    candidate_messages = [
        expected_message,
        f"Sign in to Arthentic\nAddress: {address}\nNonce: {expected_nonce}",
        expected_nonce,
    ]

    is_valid = False
    for msg in candidate_messages:
        if not msg:
            continue
        try:
            signable = encode_defunct(text=msg)
            recovered = Account.recover_message(signable, signature=req.signature).lower()
            if recovered == address:
                is_valid = True
                break
        except Exception:
            continue

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_SIGNATURE", "message": "Signature verification failed"}},
        )

    # Consume challenge nonce to prevent replay attacks
    store.challenges.pop(address, None)

    session_token = str(uuid.uuid4())
    roles = ["Collector", "Verifier", "Conservator"]
    store.sessions[session_token] = {
        "address": address,
        "roles": roles
    }

    return VerifyResponse(session=session_token, roles=roles)
