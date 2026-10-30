import hashlib
import secrets
from datetime import timedelta
from typing import Optional, List, Dict, Any
import jwt
from server.config import settings
from server.auth.clock import get_current_time

def create_access_token(user_id: str, session_id: str, roles: Optional[List[str]] = None) -> str:
    now = get_current_time()
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "sid": session_id,
        "roles": roles or [],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    kid, secret = settings.get_signing_key()
    return jwt.encode(
        payload,
        secret,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": kid},
    )

def decode_access_token(token: str) -> Dict[str, Any]:
    # Multi-key verification with kid header lookup
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        secret = settings.get_verification_key(kid)
    except KeyError:
        raise jwt.InvalidTokenError(f"Token signed with unknown key id (kid: {kid})")
    except Exception:
        # Fallback to active key if header parsing or kid missing
        secret = settings.JWT_SECRET_KEY

    return jwt.decode(
        token,
        secret,
        algorithms=[settings.JWT_ALGORITHM],
        options={"verify_exp": True},
        leeway=10,
    )

def generate_refresh_token() -> str:
    # 256 bits of cryptographically secure randomness
    return secrets.token_urlsafe(32)

def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

