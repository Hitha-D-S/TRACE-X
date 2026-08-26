"""
TRACE-X Security — JWT auth + role-based access.
Demo mode: a static demo token is accepted for hackathon convenience.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

ROLES = {"admin", "investigator", "reviewer"}

# ── Demo credentials (for hackathon only) ───────────────────
DEMO_USERS = {
    "admin@tracex.demo": {
        "id": "usr-admin-001",
        "email": "admin@tracex.demo",
        "name": "Demo Admin",
        "role": "admin",
        "hashed_password": pwd_context.hash("tracex-admin"),
    },
    "investigator@tracex.demo": {
        "id": "usr-inv-001",
        "email": "investigator@tracex.demo",
        "name": "Demo Investigator",
        "role": "investigator",
        "hashed_password": pwd_context.hash("tracex-inv"),
    },
    "reviewer@tracex.demo": {
        "id": "usr-rev-001",
        "email": "reviewer@tracex.demo",
        "name": "Demo Reviewer",
        "role": "reviewer",
        "hashed_password": pwd_context.hash("tracex-rev"),
    },
}


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def authenticate_user(email: str, password: str) -> Optional[dict]:
    user = DEMO_USERS.get(email)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """FastAPI dependency — returns current authenticated user or raises 401."""
    if credentials is None:
        # Demo mode: auto-authenticate as investigator when no token supplied
        return DEMO_USERS["investigator@tracex.demo"]

    try:
        payload = decode_token(credentials.credentials)
        email: str = payload.get("sub", "")
        user = DEMO_USERS.get(email)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate token")


def require_role(*roles: str):
    """Dependency factory that enforces one of the given roles."""
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not permitted for this operation",
            )
        return user
    return _check
