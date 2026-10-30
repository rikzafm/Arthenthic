import uuid
from datetime import timedelta
from typing import Optional, Dict, Any, Callable
from sqlalchemy.orm import Session as DBSession
from fastapi import HTTPException, status
import jwt

from server.config import settings
from server.db.models import User, Device, Session, RefreshToken, AuthIdentity
from server.auth.clock import get_current_time
from server.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from server.auth.service import create_audit_entry, get_user_roles

from jwt import PyJWKClient

JWKS_URLS = {
    "google": "https://www.googleapis.com/oauth2/v3/certs",
    "apple": "https://appleid.apple.com/auth/keys",
}

_jwks_clients: Dict[str, Any] = {
    p: PyJWKClient(url, cache_jwk_set=True, lifespan=3600)
    for p, url in JWKS_URLS.items()
}

def set_jwks_client(provider: str, client: Any):
    """
    Injects a JWKS client for a given provider (e.g., for offline testing).
    """
    _jwks_clients[provider.lower()] = client

def reset_jwks_clients():
    """
    Resets JWKS clients to default public endpoints.
    """
    global _jwks_clients
    _jwks_clients = {
        p: PyJWKClient(url, cache_jwk_set=True, lifespan=3600)
        for p, url in JWKS_URLS.items()
    }

def verify_oauth_token(provider: str, id_token: str) -> Dict[str, Any]:
    """
    Verifies an OAuth ID token (Google or Apple) using RS256 JWKS public keys.
    Returns a dict with: sub, email, email_verified, display_name.
    """

    prov_key = provider.lower()
    jwks_client = _jwks_clients.get(prov_key)
    if not jwks_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "UNSUPPORTED_OAUTH_PROVIDER", "message": f"Unsupported OAuth provider: {provider}"}}
        )

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_signature": True, "verify_aud": False},
        )
        sub = payload.get("sub")
        email = payload.get("email", "")
        email_verified = payload.get("email_verified", True)
        name = payload.get("name") or payload.get("given_name")
        if not sub:
            raise ValueError("Token missing sub claim")
        return {
            "sub": str(sub),
            "email": email,
            "email_verified": email_verified,
            "display_name": name,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_OAUTH_TOKEN", "message": f"Invalid {provider} token: {str(e)}"}}
        )

def authenticate_oauth(
    db: DBSession,
    provider: str,
    id_token: str,
    install_id: Optional[str] = None,
    device_name: Optional[str] = None,
    platform: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    token_claims = verify_oauth_token(provider, id_token)
    provider_subject = token_claims["sub"]
    raw_email = token_claims.get("email", "")
    norm_email = raw_email.strip().lower() if raw_email else None
    email_verified = token_claims.get("email_verified", False)
    display_name = token_claims.get("display_name")

    now = get_current_time()

    # 1. Check if identity already exists by (provider, provider_subject)
    identity = db.query(AuthIdentity).filter(
        AuthIdentity.provider == provider,
        AuthIdentity.provider_subject == provider_subject,
    ).first()

    if identity:
        # Returning user
        user = db.query(User).filter(User.id == identity.user_id).first()
        if not user or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "ACCOUNT_INACTIVE", "message": "Account is inactive or disabled."}}
            )
        user.last_login_at = now
        action = f"AUTH_{provider.upper()}_LOGIN"
    else:
        # Identity not found.
        # Check if user with this email already exists
        user = None
        if norm_email:
            user = db.query(User).filter(User.email == norm_email).first()

        if user:
            # Auto-link security rule:
            # Only auto-link if token's email is verified AND the existing account's email is verified!
            if not email_verified or user.email_verified_at is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "ACCOUNT_LINK_VERIFICATION_REQUIRED",
                            "message": "An account with this email exists. Please sign in with your password to link your account.",
                        }
                    }
                )

            # Link identity to existing verified user
            identity = AuthIdentity(
                id=str(uuid.uuid4()),
                user_id=user.id,
                provider=provider,
                provider_subject=provider_subject,
                email_at_link=norm_email,
                created_at=now,
            )
            db.add(identity)
            user.last_login_at = now
            action = f"AUTH_{provider.upper()}_LINK"
        else:
            # Create new user
            if not norm_email:
                # Fallback email if Apple private relay or provider omitted email
                norm_email = f"{provider_subject}@{provider}.arthentic.io"

            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                email=norm_email,
                display_name=display_name or norm_email.split("@")[0],
                password_hash=None,  # OAuth only user
                email_verified_at=now if email_verified else None,
                status="active",
                created_at=now,
                last_login_at=now,
            )
            db.add(user)

            identity = AuthIdentity(
                id=str(uuid.uuid4()),
                user_id=user_id,
                provider=provider,
                provider_subject=provider_subject,
                email_at_link=norm_email,
                created_at=now,
            )
            db.add(identity)
            action = f"AUTH_{provider.upper()}_SIGNUP"

    # Device handling
    device_obj = None
    if install_id:
        device_obj = db.query(Device).filter(Device.user_id == user.id, Device.install_id == install_id).first()
        if not device_obj:
            device_obj = Device(
                id=str(uuid.uuid4()),
                user_id=user.id,
                install_id=install_id,
                name=device_name,
                platform=platform,
                created_at=now,
                last_seen_at=now,
            )
            db.add(device_obj)
        else:
            device_obj.last_seen_at = now

    # Session & Tokens
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
        target_type="user",
        target_id=user.id,
        ip=ip,
        device_id=device_obj.id if device_obj else None,
        meta={"provider": provider, "provider_subject": provider_subject},
    )

    db.commit()

    roles = get_user_roles(db, user.id)
    access_token = create_access_token(user_id=user.id, session_id=session_id, roles=roles)

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
        }
    }

def link_oauth_identity(
    db: DBSession,
    current_user: User,
    provider: str,
    id_token: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    token_claims = verify_oauth_token(provider, id_token)
    provider_subject = token_claims["sub"]
    email = token_claims.get("email")

    # Check if identity is already linked to anyone
    existing = db.query(AuthIdentity).filter(
        AuthIdentity.provider == provider,
        AuthIdentity.provider_subject == provider_subject,
    ).first()

    if existing:
        if existing.user_id == current_user.id:
            return {"status": "ok", "message": f"{provider} is already linked to this account."}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "IDENTITY_ALREADY_LINKED", "message": f"This {provider} account is already linked to another user."}}
        )

    now = get_current_time()
    identity = AuthIdentity(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        provider=provider,
        provider_subject=provider_subject,
        email_at_link=email,
        created_at=now,
    )
    db.add(identity)

    create_audit_entry(
        db,
        action=f"AUTH_{provider.upper()}_LINKED",
        actor_user_id=current_user.id,
        target_type="user",
        target_id=current_user.id,
        ip=ip,
        meta={"provider": provider, "provider_subject": provider_subject},
    )

    db.commit()
    return {"status": "ok", "provider": provider}

