"""Auth API — registration, login, platform binding."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import (
    authenticate_by_password,
    create_access_token,
    generate_api_key,
    get_current_user_jwt,
    hash_password,
    resolve_user_by_platform,
)
from app.infra.db import get_db
from app.models.db_models import PlatformBinding, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Request schemas ---


class RegisterRequest(BaseModel):
    username: str
    platform: str | None = None
    platform_uid: str | None = None
    password: str | None = None
    email: str | None = None


class PlatformLoginRequest(BaseModel):
    platform: str
    platform_uid: str


class ApiKeyLoginRequest(BaseModel):
    api_key: str


class PasswordLoginRequest(BaseModel):
    username: str
    password: str


class BindPlatformRequest(BaseModel):
    platform: str
    platform_uid: str


# --- Endpoints ---


@router.post("/register")
async def register(
    req: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Register a new user with optional platform binding and/or password."""
    has_platform = req.platform is not None and req.platform_uid is not None
    has_password = req.password is not None

    if not has_platform and not has_password:
        raise HTTPException(
            status_code=400,
            detail="Must provide either platform+platform_uid or password",
        )

    if has_platform:
        existing = await resolve_user_by_platform(db, req.platform, req.platform_uid)
        if existing is not None:
            raise HTTPException(status_code=409, detail="Platform identity already registered")

    raw_key, key_hash = generate_api_key()
    password_hash_value = hash_password(req.password) if has_password else None

    user = User(
        username=req.username,
        api_key_hash=key_hash,
        password_hash=password_hash_value,
        email=req.email,
    )
    db.add(user)
    await db.flush()

    if has_platform:
        binding = PlatformBinding(
            user_id=user.id, platform=req.platform, platform_uid=req.platform_uid
        )
        db.add(binding)
        await db.flush()

    token = create_access_token(user.id)

    return {
        "user_id": user.id,
        "api_key": raw_key,
        "access_token": token.access_token,
        "expires_at": token.expires_at.isoformat(),
    }


@router.post("/login/platform")
async def login_by_platform(
    req: PlatformLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Login via platform identity (used by bot middleware)."""
    user = await resolve_user_by_platform(db, req.platform, req.platform_uid)
    if user is None:
        raise HTTPException(status_code=404, detail="No user bound to this platform identity")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    token = create_access_token(user.id)
    return {
        "user_id": user.id,
        "access_token": token.access_token,
        "expires_at": token.expires_at.isoformat(),
    }


@router.post("/login/api-key")
async def login_by_api_key(
    req: ApiKeyLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Login via API key. Returns JWT token."""
    key_hash = hashlib.sha256(req.api_key.encode()).hexdigest()
    result = await db.execute(select(User).where(User.api_key_hash == key_hash))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated")

    token = create_access_token(user.id)
    return {
        "user_id": user.id,
        "access_token": token.access_token,
        "expires_at": token.expires_at.isoformat(),
    }


@router.post("/login/password")
async def login_by_password(
    req: PasswordLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Login via username + password. Returns JWT token."""
    user = await authenticate_by_password(db, req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user.id)
    return {
        "user_id": user.id,
        "access_token": token.access_token,
        "expires_at": token.expires_at.isoformat(),
    }


@router.post("/bind-platform")
async def bind_platform(
    req: BindPlatformRequest,
    user: Annotated[User, Depends(get_current_user_jwt)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Bind an additional platform identity to the authenticated user."""
    existing = await db.execute(
        select(PlatformBinding).where(
            PlatformBinding.platform == req.platform,
            PlatformBinding.platform_uid == req.platform_uid,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Platform identity already bound")

    binding = PlatformBinding(
        user_id=user.id, platform=req.platform, platform_uid=req.platform_uid
    )
    db.add(binding)
    await db.flush()

    return {
        "user_id": user.id,
        "platform": req.platform,
        "platform_uid": req.platform_uid,
        "status": "bound",
    }


@router.get("/me")
async def get_me(
    user: Annotated[User, Depends(get_current_user_jwt)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the current authenticated user's profile and bindings."""
    bindings_result = await db.execute(
        select(PlatformBinding).where(PlatformBinding.user_id == user.id)
    )
    bindings = bindings_result.scalars().all()

    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "platform_bindings": [
            {
                "platform": b.platform,
                "platform_uid": b.platform_uid,
                "bound_at": b.bound_at.isoformat(),
            }
            for b in bindings
        ],
    }
