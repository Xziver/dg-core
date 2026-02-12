"""Admin authentication backend for sqladmin."""

from __future__ import annotations

import hashlib

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.infra.auth import create_access_token, decode_access_token
from app.infra.db import async_session_factory
from app.models.db_models import User

from sqlalchemy import select


class AdminAuth(AuthenticationBackend):
    """Authenticate admin users via API key login, stored as JWT in session."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        api_key = str(form.get("password", ""))
        if not api_key:
            return False

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        async with async_session_factory() as db:
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
