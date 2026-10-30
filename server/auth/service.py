import uuid
from datetime import timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session as DBSession
from fastapi import HTTPException, status

from server.config import settings
from server.db.models import (
    User,
    Device,
    Session,
    RefreshToken,
    AuditLog,
    RoleAssignment,
    ActionToken,
    AuthIdentity,
)
from server.auth.clock import get_current_time, ensure_utc
from server.auth.password import hash_password, verify_password, validate_password_strength
from server.auth.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    decode_access_token,
)
from server.auth.limiter import limiter
from server.auth.monitoring import monitoring

VALID_ACCREDITED_ROLES = {"Artist", "Gallery", "Conservator", "Admin"}

def normalize_role(role_name: str) -> str:
    r = role_name.strip()
    if r.lower() in ("verifier", "gallery"):
        return "Gallery"
    return r.capitalize()

def get_user_roles(db: DBSession, user_id: str) -> List[str]:
    """
    Returns active roles for a user.
    Every registered user implicitly holds the 'Collector' role.
    Additional roles are held via active entries in role_assignments.
    """
    assignments = db.query(RoleAssignment).filter(
        RoleAssignment.user_id == user_id,
        RoleAssignment.status == "active",
    ).all()
    roles = {"Collector"}
    for a in assignments:
        roles.add(normalize_role(a.role))

    order = ["Collector", "Artist", "Gallery", "Conservator", "Admin"]
    return sorted(list(roles), key=lambda x: order.index(x) if x in order else 99)

def grant_user_role(
    db: DBSession,
    user_id: str,
    role: str,
    granted_by_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> RoleAssignment:
    normalized = normalize_role(role)
    if normalized not in VALID_ACCREDITED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_ROLE", "message": f"Role '{role}' is not a valid accredited role."}}
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "Target user not found."}}
        )

    # Prevent Admin from approving/granting to themselves if granted_by_id is provided
    if granted_by_id and granted_by_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "SELF_GRANT_FORBIDDEN", "message": "Admins cannot self-grant accredited roles."}}
        )

    # Check for existing active assignment
    existing = db.query(RoleAssignment).filter(
        RoleAssignment.user_id == user_id,
        RoleAssignment.role == normalized,
        RoleAssignment.status == "active",
    ).first()
    if existing:
        return existing

    assignment = RoleAssignment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        role=normalized,
        status="active",
        granted_by=granted_by_id,
        granted_at=get_current_time(),
    )
    db.add(assignment)

    create_audit_entry(
        db,
        action="ROLE_GRANTED",
        actor_user_id=granted_by_id,
        target_type="role_assignment",
        target_id=assignment.id,
        ip=ip,
        meta={"user_id": user_id, "role": normalized},
    )
    db.commit()
    return assignment

def revoke_user_role(
    db: DBSession,
    user_id: str,
    role: str,
    revoked_by_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> bool:
    normalized = normalize_role(role)
    if normalized == "Collector":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "CANNOT_REVOKE_COLLECTOR", "message": "Collector role cannot be revoked from a registered user."}}
        )

    # Guard: Last Admin cannot be revoked
    if normalized == "Admin":
        active_admins = db.query(RoleAssignment).filter(
            RoleAssignment.role == "Admin",
            RoleAssignment.status == "active",
        ).count()
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "LAST_ADMIN_PROTECTED", "message": "Cannot revoke the last active Admin account."}}
            )

    assignment = db.query(RoleAssignment).filter(
        RoleAssignment.user_id == user_id,
        RoleAssignment.role == normalized,
        RoleAssignment.status == "active",
    ).first()

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ROLE_NOT_ASSIGNED", "message": f"User does not hold active role '{normalized}'."}}
        )

    now = get_current_time()
    assignment.status = "revoked"
    assignment.revoked_at = now

    # Admin revoke also kills user's active sessions (Section 4 edge cases)
    active_sessions = db.query(Session).filter(
        Session.user_id == user_id,
        Session.revoked_at.is_(None),
    ).all()
    for s in active_sessions:
        s.revoked_at = now
        s.revoke_reason = f"ROLE_REVOKED_{normalized}"

    create_audit_entry(
        db,
        action="ROLE_REVOKED",
        actor_user_id=revoked_by_id,
        target_type="role_assignment",
        target_id=assignment.id,
        ip=ip,
        meta={"user_id": user_id, "role": normalized, "revoked_sessions": len(active_sessions)},
    )
    db.commit()
    return True

def create_audit_entry(
    db: DBSession,
    action: str,
    actor_user_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    ip: Optional[str] = None,
    device_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        id=str(uuid.uuid4()),
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        device_id=device_id,
        meta=meta or {},
        created_at=get_current_time(),
    )
    db.add(entry)
    return entry

def signup_user(
    db: DBSession,
    email: str,
    password: str,
    display_name: Optional[str] = None,
    install_id: Optional[str] = None,
    device_name: Optional[str] = None,
    platform: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    # Rate limit check by IP
    if ip and limiter.is_rate_limited(f"signup:ip:{ip}", settings.RATE_LIMIT_SIGNUP_ATTEMPTS, settings.RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many signup attempts. Please try again later."}}
        )
    if ip:
        limiter.record_attempt(f"signup:ip:{ip}")

    # Validate password
    is_valid, msg = validate_password_strength(password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "WEAK_PASSWORD", "message": msg}}
        )

    norm_email = email.strip().lower()
    if "@" not in norm_email or "." not in norm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_EMAIL", "message": "Invalid email address."}}
        )

    # Check if user exists
    existing = db.query(User).filter(User.email == norm_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMAIL_TAKEN", "message": "An account with this email already exists."}}
        )

    now = get_current_time()
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=norm_email,
        display_name=display_name or norm_email.split("@")[0],
        password_hash=hash_password(password),
        status="active",
        created_at=now,
        last_login_at=now,
    )
    db.add(user)

    # Register device if install_id given
    device_obj = None
    if install_id:
        device_obj = Device(
            id=str(uuid.uuid4()),
            user_id=user_id,
            install_id=install_id,
            name=device_name,
            platform=platform,
            created_at=now,
            last_seen_at=now,
        )
        db.add(device_obj)

    # Create session with 30-day absolute expiration
    session_id = str(uuid.uuid4())
    abs_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session_obj = Session(
        id=session_id,
        user_id=user_id,
        device_id=device_obj.id if device_obj else None,
        absolute_expires_at=abs_expires,
        created_at=now,
    )
    db.add(session_obj)

    # Create initial refresh token
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

    # Audit log
    create_audit_entry(
        db,
        action="AUTH_SIGNUP",
        actor_user_id=user_id,
        target_type="user",
        target_id=user_id,
        ip=ip,
        device_id=device_obj.id if device_obj else None,
        meta={"email": norm_email},
    )

    db.commit()

    roles = get_user_roles(db, user_id)
    access_token = create_access_token(user_id=user_id, session_id=session_id, roles=roles)

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

def login_user(
    db: DBSession,
    email: str,
    password: str,
    install_id: Optional[str] = None,
    device_name: Optional[str] = None,
    platform: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    norm_email = email.strip().lower()

    # Rate limit check by IP & email
    ip_key = f"login:ip:{ip}" if ip else None
    email_key = f"login:email:{norm_email}"

    if (ip_key and limiter.is_rate_limited(ip_key, settings.RATE_LIMIT_LOGIN_ATTEMPTS, settings.RATE_LIMIT_WINDOW_SECONDS)) or \
       limiter.is_rate_limited(email_key, settings.RATE_LIMIT_LOGIN_ATTEMPTS, settings.RATE_LIMIT_WINDOW_SECONDS):
        monitoring.record_rate_limit("login")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many login attempts. Please try again later."}}
        )

    user = db.query(User).filter(User.email == norm_email).first()
    if not user or not user.password_hash or not verify_password(user.password_hash, password):
        monitoring.record_login_failure("invalid_credentials")
        if ip_key:
            limiter.record_attempt(ip_key)
        limiter.record_attempt(email_key)
        create_audit_entry(
            db,
            action="AUTH_LOGIN_FAILED",
            actor_user_id=user.id if user else None,
            target_type="user",
            target_id=user.id if user else None,
            ip=ip,
            meta={"email": norm_email},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}}
        )

    if user.status != "active":
        monitoring.record_login_failure("account_inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "ACCOUNT_INACTIVE", "message": f"Account is {user.status}."}}
        )

    # Success: reset email rate limit
    limiter.reset(email_key)
    monitoring.record_login_success()

    now = get_current_time()
    user.last_login_at = now

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
            if device_name:
                device_obj.name = device_name
            if platform:
                device_obj.platform = platform

    # Create session with 30-day absolute expiration
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

    # Initial refresh token
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
        action="AUTH_LOGIN",
        actor_user_id=user.id,
        target_type="session",
        target_id=session_id,
        ip=ip,
        device_id=device_obj.id if device_obj else None,
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

def refresh_tokens(
    db: DBSession,
    raw_refresh_token: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    token_hash = hash_refresh_token(raw_refresh_token)
    token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if not token:
        monitoring.record_refresh_failure("not_found")
        create_audit_entry(
            db,
            action="AUTH_REFRESH_NOT_FOUND",
            ip=ip,
            meta={"token_hash": token_hash[:8] + "..."},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token."}}
        )

    session = db.query(Session).filter(Session.id == token.session_id).first()
    now = get_current_time()

    # Reuse detection check
    if token.used_at is not None:
        monitoring.record_token_reuse(user_id=session.user_id if session else None)
        monitoring.record_refresh_failure("reuse_detected")
        # Revoke the session and token family!
        if session:
            session.revoked_at = now
            session.revoke_reason = "REUSE_DETECTED"
        create_audit_entry(
            db,
            action="AUTH_REUSE_DETECTED",
            actor_user_id=session.user_id if session else None,
            target_type="session",
            target_id=session.id if session else None,
            ip=ip,
            meta={"family_id": token.family_id, "token_id": token.id},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_REUSE_DETECTED", "message": "Refresh token reuse detected. Session revoked for security."}}
        )

    # Check session revoked or expired
    if not session or session.revoked_at is not None:
        monitoring.record_refresh_failure("session_revoked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "SESSION_REVOKED", "message": "Session has been revoked."}}
        )

    # Absolute 30-day cap check
    if ensure_utc(session.absolute_expires_at) <= now:
        monitoring.record_refresh_failure("session_expired_30d_cap")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "SESSION_EXPIRED", "message": "Session expired (30-day cap reached). Please sign in again."}}
        )

    if ensure_utc(token.expires_at) <= now:
        monitoring.record_refresh_failure("refresh_token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "REFRESH_TOKEN_EXPIRED", "message": "Refresh token expired."}}
        )

    # Rotate token
    token.used_at = now

    new_raw = generate_refresh_token()
    new_expires = min(now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), ensure_utc(session.absolute_expires_at))
    new_token = RefreshToken(
        id=str(uuid.uuid4()),
        session_id=session.id,
        token_hash=hash_refresh_token(new_raw),
        family_id=token.family_id,
        expires_at=new_expires,
        created_at=now,
    )
    db.add(new_token)
    token.replaced_by = new_token.id

    create_audit_entry(
        db,
        action="AUTH_REFRESH",
        actor_user_id=session.user_id,
        target_type="session",
        target_id=session.id,
        ip=ip,
    )

    db.commit()

    roles = get_user_roles(db, session.user_id)
    new_access_token = create_access_token(user_id=session.user_id, session_id=session.id, roles=roles)
    monitoring.record_refresh_success()

    return {
        "access_token": new_access_token,
        "refresh_token": new_raw,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }

def logout_session(
    db: DBSession,
    session_id: str,
    user_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    session = db.query(Session).filter(Session.id == session_id).first()
    if session:
        session.revoked_at = get_current_time()
        session.revoke_reason = "USER_LOGOUT"
        create_audit_entry(
            db,
            action="AUTH_LOGOUT",
            actor_user_id=user_id or session.user_id,
            target_type="session",
            target_id=session.id,
            ip=ip,
        )
        db.commit()
    return {"status": "ok"}

def list_user_sessions(
    db: DBSession,
    user_id: str,
    current_session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sessions = db.query(Session).filter(Session.user_id == user_id).order_by(Session.created_at.desc()).all()
    results = []
    now = get_current_time()
    for s in sessions:
        device = s.device
        is_active = s.revoked_at is None and ensure_utc(s.absolute_expires_at) > now
        results.append({
            "id": s.id,
            "device_id": s.device_id,
            "device_name": device.name if device else "Unknown Device",
            "platform": device.platform if device else "unknown",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "last_seen_at": device.last_seen_at.isoformat() if device and device.last_seen_at else None,
            "is_current": s.id == current_session_id,
            "is_active": is_active,
            "revoked_at": s.revoked_at.isoformat() if s.revoked_at else None,
            "revoke_reason": s.revoke_reason,
        })
    return results

def revoke_user_session(
    db: DBSession,
    user_id: str,
    session_id: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    session = db.query(Session).filter(Session.id == session_id, Session.user_id == user_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SESSION_NOT_FOUND", "message": "Session not found."}}
        )
    if session.revoked_at is None:
        now = get_current_time()
        session.revoked_at = now
        session.revoke_reason = "USER_REMOTE_REVOKE"
        create_audit_entry(
            db,
            action="SESSION_REVOKED",
            actor_user_id=user_id,
            target_type="session",
            target_id=session.id,
            ip=ip,
            device_id=session.device_id,
        )
        db.commit()
    return {"status": "ok", "revoked_session_id": session_id}

def change_user_password(
    db: DBSession,
    user_id: str,
    new_password: str,
    current_password: Optional[str] = None,
    current_session_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}}
        )

    # If user currently has a password, verify current_password
    if user.password_hash:
        if not current_password or not verify_password(user.password_hash, current_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "INVALID_CURRENT_PASSWORD", "message": "Current password is incorrect."}}
            )

    # Validate new password strength
    is_valid, msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "WEAK_PASSWORD", "message": msg}}
        )

    user.password_hash = hash_password(new_password)
    now = get_current_time()

    # Revoke all other active sessions for security
    other_sessions = db.query(Session).filter(
        Session.user_id == user_id,
        Session.id != current_session_id,
        Session.revoked_at.is_(None),
    ).all()
    for s in other_sessions:
        s.revoked_at = now
        s.revoke_reason = "PASSWORD_CHANGED"

    create_audit_entry(
        db,
        action="PASSWORD_CHANGED",
        actor_user_id=user_id,
        target_type="user",
        target_id=user_id,
        ip=ip,
    )
    db.commit()
    return {"status": "ok", "message": "Password changed successfully. Other sessions have been revoked."}

def request_password_reset(
    db: DBSession,
    email: str,
    ip: Optional[str] = None,
) -> Optional[str]:
    clean_email = email.lower().strip()
    if limiter.is_rate_limited(f"pwd_reset_{clean_email}", max_attempts=5, window_seconds=600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMITED", "message": "Too many password reset requests. Please try again later."}}
        )
    limiter.record_attempt(f"pwd_reset_{clean_email}")

    user = db.query(User).filter(User.email == clean_email).first()
    raw_token = None
    if user and user.status == "active":
        raw_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_token)
        now = get_current_time()
        action_token = ActionToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=token_hash,
            purpose="password_reset",
            expires_at=now + timedelta(hours=1),
            created_at=now,
        )
        db.add(action_token)
        create_audit_entry(
            db,
            action="PASSWORD_RESET_REQUESTED",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
            ip=ip,
        )
        db.commit()
    else:
        create_audit_entry(
            db,
            action="PASSWORD_RESET_ATTEMPT_UNKNOWN_EMAIL",
            ip=ip,
            meta={"email": clean_email[:3] + "..."},
        )
        db.commit()
    return raw_token

def confirm_password_reset(
    db: DBSession,
    raw_token: str,
    new_password: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    token_hash = hash_refresh_token(raw_token)
    now = get_current_time()
    action_token = db.query(ActionToken).filter(
        ActionToken.token_hash == token_hash,
        ActionToken.purpose == "password_reset",
    ).first()

    if not action_token or action_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_RESET_TOKEN", "message": "Password reset token is invalid or has already been used."}}
        )

    if ensure_utc(action_token.expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EXPIRED_RESET_TOKEN", "message": "Password reset token has expired."}}
        )

    user = db.query(User).filter(User.id == action_token.user_id).first()
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "USER_NOT_ACTIVE", "message": "Associated account is not active."}}
        )

    is_valid, msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "WEAK_PASSWORD", "message": msg}}
        )

    user.password_hash = hash_password(new_password)
    action_token.used_at = now

    # Revoke ALL active sessions for this user on reset
    active_sessions = db.query(Session).filter(
        Session.user_id == user.id,
        Session.revoked_at.is_(None),
    ).all()
    for s in active_sessions:
        s.revoked_at = now
        s.revoke_reason = "PASSWORD_RESET"

    create_audit_entry(
        db,
        action="PASSWORD_RESET_COMPLETED",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=ip,
    )
    db.commit()
    return {"status": "ok", "message": "Password reset successfully. Please log in with your new password."}

def request_email_verification(
    db: DBSession,
    user_id: str,
    ip: Optional[str] = None,
) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}}
        )

    if limiter.is_rate_limited(f"email_verify_{user_id}", max_attempts=5, window_seconds=600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "RATE_LIMITED", "message": "Too many verification requests. Please try again later."}}
        )
    limiter.record_attempt(f"email_verify_{user_id}")

    raw_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_token)
    now = get_current_time()
    action_token = ActionToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=token_hash,
        purpose="email_verification",
        expires_at=now + timedelta(hours=24),
        created_at=now,
    )
    db.add(action_token)
    create_audit_entry(
        db,
        action="EMAIL_VERIFICATION_REQUESTED",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=ip,
    )
    db.commit()
    return raw_token

def confirm_email_verification(
    db: DBSession,
    raw_token: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    token_hash = hash_refresh_token(raw_token)
    now = get_current_time()
    action_token = db.query(ActionToken).filter(
        ActionToken.token_hash == token_hash,
        ActionToken.purpose == "email_verification",
    ).first()

    if not action_token or action_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_VERIFY_TOKEN", "message": "Verification token is invalid or has already been used."}}
        )

    if ensure_utc(action_token.expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EXPIRED_VERIFY_TOKEN", "message": "Verification token has expired."}}
        )

    user = db.query(User).filter(User.id == action_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}}
        )

    user.email_verified_at = now
    action_token.used_at = now

    create_audit_entry(
        db,
        action="EMAIL_VERIFIED",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=ip,
    )
    db.commit()
    return {"status": "ok", "message": "Email verified successfully."}

def delete_user_account(
    db: DBSession,
    user_id: str,
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}}
        )

    now = get_current_time()

    user.status = "deleted"
    anon_tag = uuid.uuid4().hex[:12]
    user.email = f"deleted_{anon_tag}@deleted.arthentic.io"
    user.display_name = "Deleted Account"
    user.password_hash = None

    sessions = db.query(Session).filter(Session.user_id == user_id, Session.revoked_at.is_(None)).all()
    for s in sessions:
        s.revoked_at = now
        s.revoke_reason = "ACCOUNT_DELETED"

    db.query(AuthIdentity).filter(AuthIdentity.user_id == user_id).delete()

    create_audit_entry(
        db,
        action="ACCOUNT_DELETED",
        actor_user_id=user_id,
        target_type="user",
        target_id=user_id,
        ip=ip,
    )
    db.commit()
    return {"status": "ok", "message": "Account successfully deleted."}

def get_user_audit_log(
    db: DBSession,
    user_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    entries = db.query(AuditLog).filter(
        (AuditLog.actor_user_id == user_id) | (AuditLog.target_id == user_id)
    ).order_by(AuditLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "ip": e.ip,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "meta": e.meta,
        }
        for e in entries
    ]

def get_admin_audit_log(
    db: DBSession,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    entries = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "action": e.action,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "ip": e.ip,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "meta": e.meta,
        }
        for e in entries
    ]
