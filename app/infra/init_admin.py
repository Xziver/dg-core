"""Auto-create default admin user on first launch."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.infra.auth import generate_api_key, hash_password
from app.infra.config import settings
from app.models.db_models import User

logger = logging.getLogger("dg-core.init_admin")


async def ensure_default_admin(session_factory) -> None:
    """Create the default admin user if configured and not already present.

    Idempotent: if a user with the configured username already exists,
    logs a message and does nothing.

    Args:
        session_factory: An async_sessionmaker to create DB sessions.
    """
    username = settings.default_admin_username.strip()
    if not username:
        logger.debug("DEFAULT_ADMIN_USERNAME not set — skipping default admin creation.")
        return

    password = settings.default_admin_password
    email = settings.default_admin_email

    if not settings.app_debug and not password:
        logger.warning(
            "DEFAULT_ADMIN_PASSWORD is empty in non-debug mode. "
            "The admin user will only be accessible via API key."
        )

    async with session_factory() as db:
        result = await db.execute(
            select(User).where(User.username == username)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            logger.info(
                "Default admin user '%s' already exists (id=%s, role=%s). Skipping.",
                username,
                existing.id,
                existing.role,
            )
            return

        raw_api_key, api_key_hash = generate_api_key()
        password_hash_value = hash_password(password) if password else None

        user = User(
            username=username,
            email=email,
            api_key_hash=api_key_hash,
            password_hash=password_hash_value,
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.commit()

        logger.info("=" * 60)
        logger.info("DEFAULT ADMIN USER CREATED")
        logger.info("=" * 60)
        logger.info("  Username : %s", username)
        logger.info("  User ID  : %s", user.id)
        logger.info("  API Key  : %s", raw_api_key)
        if password:
            logger.info("  Password : (set from DEFAULT_ADMIN_PASSWORD)")
        else:
            logger.info("  Password : (not set — use API key for admin login)")
        if email:
            logger.info("  Email    : %s", email)
        logger.info("=" * 60)
        logger.info(
            "IMPORTANT: Save the API key above. It will NOT be shown again."
        )
        logger.info("=" * 60)
