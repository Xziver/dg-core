"""Admin authentication backend for sqladmin."""

from __future__ import annotations

import hashlib

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.infra.auth import create_access_token, decode_access_token, verify_password
from app.infra.db import async_session_factory
from app.models.db_models import User

from sqlalchemy import select


class AdminAuth(AuthenticationBackend):
    """Authenticate admin users via password or API key, stored as JWT in session."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))
        if not password:
            return False

        async with async_session_factory() as db:
            user = None

            # Strategy 1: Try password auth if username is provided
            if username:
                result = await db.execute(
                    select(User).where(
                        User.username == username,
                        User.role == "admin",
                        User.is_active == True,  # noqa: E712
                    )
                )
                candidate = result.scalar_one_or_none()
                if candidate and candidate.password_hash:
                    if verify_password(password, candidate.password_hash):
                        user = candidate

            # Strategy 2: Fall back to API key auth
            if user is None:
                key_hash = hashlib.sha256(password.encode()).hexdigest()
                result = await db.execute(
                    select(User).where(
                        User.api_key_hash == key_hash,
                        User.role == "admin",
                        User.is_active == True,  # noqa: E712
                    )
                )
                user = result.scalar_one_or_none()

            if user is None:
                return False

            token = create_access_token(user.id)
            request.session["token"] = token.access_token
            request.session["user_id"] = user.id
            return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        if not token:
            return False
        try:
            token_data = decode_access_token(token)
        except Exception:
            return False

        async with async_session_factory() as db:
            result = await db.execute(
                select(User).where(
                    User.id == token_data.user_id,
                    User.role == "admin",
                    User.is_active == True,  # noqa: E712
                )
            )
            user = result.scalar_one_or_none()
            return user is not None
