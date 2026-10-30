from typing import Tuple, Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session as DBSession
from jwt.exceptions import PyJWTError, ExpiredSignatureError

from server.db.database import get_db
from server.db.models import User, Session
from server.auth.tokens import decode_access_token
from server.auth.clock import get_current_time, ensure_utc
from server.auth.service import get_user_roles, normalize_role

def get_token_from_header(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "MISSING_AUTHORIZATION", "message": "Authorization header missing."}}
        )
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN_FORMAT", "message": "Invalid Authorization header format. Expected 'Bearer <token>'."}}
        )
    return parts[1]

def get_current_user_and_session(
    token: str = Depends(get_token_from_header),
    db: DBSession = Depends(get_db),
) -> Tuple[User, Session]:
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_EXPIRED", "message": "Access token expired."}}
        )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid access token."}}
        )

    user_id = payload.get("sub")
    session_id = payload.get("sid")

    if not user_id or not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN_CLAIMS", "message": "Token claims missing."}}
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found or inactive."}}
        )

    session = db.query(Session).filter(Session.id == session_id).first()
    if not session or session.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "SESSION_REVOKED", "message": "Session has been revoked."}}
        )

    now = get_current_time()
    if ensure_utc(session.absolute_expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "SESSION_EXPIRED", "message": "Session expired."}}
        )

    return user, session

def get_current_user(auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session)) -> User:
    return auth_pair[0]

def get_current_session(auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session)) -> Session:
    return auth_pair[1]

def require_role(*required_roles: str, check_db: bool = False):
    """
    Enforces that the authenticated user holds at least one of the required roles.
    If check_db is True, queries the database directly to ensure recently revoked roles
    are not honored from a stale JWT (for sensitive operations).
    """
    def role_checker(
        auth_pair: Tuple[User, Session] = Depends(get_current_user_and_session),
        token: str = Depends(get_token_from_header),
        db: DBSession = Depends(get_db),
    ) -> User:
        user, _ = auth_pair
        normalized_required = {normalize_role(r).lower() for r in required_roles}

        if check_db:
            user_roles = get_user_roles(db, user.id)
        else:
            try:
                payload = decode_access_token(token)
                user_roles = payload.get("roles", [])
                if not user_roles:
                    user_roles = get_user_roles(db, user.id)
            except Exception:
                user_roles = get_user_roles(db, user.id)

        user_roles_normalized = {normalize_role(r).lower() for r in user_roles}
        if not any(req in user_roles_normalized for req in normalized_required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"User does not have required role: {', '.join(required_roles)}. Current roles: {user_roles}",
                    }
                },
            )
        return user

    return role_checker

def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: DBSession = Depends(get_db),
) -> Optional[User]:
    """
    Returns the authenticated User if valid Authorization header is present,
    or None if request is from an unauthenticated Guest.
    """
    if not authorization:
        return None
    try:
        token = get_token_from_header(authorization)
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        session_id = payload.get("sid")
        if not user_id or not session_id:
            return None
        user = db.query(User).filter(User.id == user_id, User.status == "active").first()
        session = db.query(Session).filter(Session.id == session_id, Session.revoked_at.is_(None)).first()
        if not user or not session:
            return None
        if ensure_utc(session.absolute_expires_at) <= get_current_time():
            return None
        return user
    except Exception:
        return None
