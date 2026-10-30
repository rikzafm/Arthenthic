import os
from typing import Dict, Tuple, Optional

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./arthentic.db")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "arthentic-dev-secret-key-at-least-32-chars-long!")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    RATE_LIMIT_LOGIN_ATTEMPTS: int = int(os.getenv("RATE_LIMIT_LOGIN_ATTEMPTS", "5"))
    RATE_LIMIT_SIGNUP_ATTEMPTS: int = int(os.getenv("RATE_LIMIT_SIGNUP_ATTEMPTS", "5"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Dual-Key Rotation Support (Milestone 7)
    JWT_ACTIVE_KID: str = os.getenv("JWT_ACTIVE_KID", "v1")
    _jwt_keys: Dict[str, str] = {}

    def __init__(self):
        self._jwt_keys = {
            self.JWT_ACTIVE_KID: self.JWT_SECRET_KEY,
        }
        sec_key = os.getenv("JWT_SECRET_KEY_SECONDARY")
        sec_kid = os.getenv("JWT_SECONDARY_KID", "v2")
        if sec_key:
            self._jwt_keys[sec_kid] = sec_key

    @property
    def JWT_KEYS(self) -> Dict[str, str]:
        return self._jwt_keys

    def get_signing_key(self) -> Tuple[str, str]:
        """Returns the current active key ID and its secret for signing new JWTs."""
        kid = self.JWT_ACTIVE_KID
        secret = self._jwt_keys.get(kid, self.JWT_SECRET_KEY)
        return kid, secret

    def get_verification_key(self, kid: Optional[str] = None) -> str:
        """Returns the secret key corresponding to the provided kid for verifying JWTs."""
        if not kid:
            return self._jwt_keys.get(self.JWT_ACTIVE_KID, self.JWT_SECRET_KEY)
        if kid in self._jwt_keys:
            return self._jwt_keys[kid]
        raise KeyError(f"Unknown JWT key ID (kid): {kid}")

    def register_key(self, kid: str, secret: str, make_active: bool = False):
        """Registers a new secret key for verification and optionally sets it as active."""
        self._jwt_keys[kid] = secret
        if make_active:
            self.JWT_ACTIVE_KID = kid

    def set_active_kid(self, kid: str):
        """Sets an already registered key ID as the active signing key."""
        if kid not in self._jwt_keys:
            raise KeyError(f"Cannot activate unregistered kid: {kid}")
        self.JWT_ACTIVE_KID = kid

settings = Settings()


