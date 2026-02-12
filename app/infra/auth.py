"""Authentication utilities — JWT tokens, API key validation, password hashing, platform lookup."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.config import settings
from app.infra.db import get_db
from app.models.db_models import PlatformBinding, User


# --- Password hashing ---


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# --- Token schemas ---


class TokenData(BaseModel):
    user_id: str
    exp: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_at: datetime


# --- API Key utilities ---


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and its hash. Returns (raw_key, hash)."""
    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify an API key against its stored hash."""
    return hashlib.sha256(raw_key.encode()).hexdigest() == key_hash


# --- JWT utilities ---


def create_access_token(user_id: str) -> TokenResponse:
    """Create a JWT access token for a user."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        expires_at=expires_at,
    )


def decode_access_token(token: str) -> TokenData:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub", "")
        exp = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        return TokenData(user_id=user_id, exp=exp)
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# --- Platform resolution ---


async def resolve_user_by_platform(
    db: AsyncSession, platform: str, platform_uid: str
) -> User | None:
    """Look up a user by platform identity."""
    result = await db.execute(
        select(User)
        .join(PlatformBinding, PlatformBinding.user_id == User.id)
        .where(
            PlatformBinding.platform == platform,
            PlatformBinding.platform_uid == platform_uid,
        )
    )
    return result.scalar_one_or_none()


async def authenticate_by_password(
    db: AsyncSession, username: str, password: str
) -> User | None:
    """Authenticate a user by username + password. Returns User or None."""
    result = await db.execute(
        select(User).where(
            User.username == username,
            User.is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# --- FastAPI Dependencies ---

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_jwt(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Dependency: extract user from JWT Bearer token."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token_data = decode_access_token(credentials.credentials)
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")
    return user


async def get_current_user_api_key(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Dependency: validate API key from X-API-Key header."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await db.execute(select(User).where(User.api_key_hash == key_hash))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")
    return user


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Flexible auth dependency: tries JWT Bearer first, then X-API-Key header.

    Bot clients use X-API-Key; web clients use Bearer JWT.
    """
    # Try Bearer token first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        token_data = decode_access_token(token)
        result = await db.execute(select(User).where(User.id == token_data.user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user

    # Try X-API-Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await db.execute(select(User).where(User.api_key_hash == key_hash))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user

    raise HTTPException(status_code=401, detail="Authentication required")
