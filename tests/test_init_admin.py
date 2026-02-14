"""Tests for default admin auto-creation."""

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.auth import verify_password
from app.infra.init_admin import ensure_default_admin
from app.models.db_models import User


def _make_settings(**overrides):
    """Return a mock settings namespace with defaults."""
    defaults = {
        "default_admin_username": "",
        "default_admin_password": "",
        "default_admin_email": None,
        "app_debug": True,
    }
    defaults.update(overrides)

    class _S:
        pass

    s = _S()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def _factory(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


async def _count_users(factory):
    async with factory() as db:
        result = await db.execute(select(User))
        return len(result.scalars().all())


async def test_ensure_default_admin_creates_user(db_engine):
    """Admin user is created with correct attributes."""
    factory = _factory(db_engine)

    with patch("app.infra.init_admin.settings", _make_settings(
        default_admin_username="admin",
        default_admin_password="testpass123",
        default_admin_email="admin@test.com",
    )):
        await ensure_default_admin(factory)

    async with factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.role == "admin"
        assert user.is_active is True
        assert user.api_key_hash is not None
        assert len(user.api_key_hash) == 64  # SHA256 hex digest
        assert user.password_hash is not None
        assert verify_password("testpass123", user.password_hash)
        assert user.email == "admin@test.com"


async def test_ensure_default_admin_skips_when_not_configured(db_engine):
    """No user created when DEFAULT_ADMIN_USERNAME is empty."""
    factory = _factory(db_engine)

    with patch("app.infra.init_admin.settings", _make_settings(
        default_admin_username="",
    )):
        await ensure_default_admin(factory)

    assert await _count_users(factory) == 0


async def test_ensure_default_admin_idempotent(db_engine):
    """Calling twice creates only one user."""
    factory = _factory(db_engine)
    mock_settings = _make_settings(
        default_admin_username="admin",
        default_admin_password="pass",
    )

    with patch("app.infra.init_admin.settings", mock_settings):
        await ensure_default_admin(factory)
        await ensure_default_admin(factory)

    assert await _count_users(factory) == 1


async def test_ensure_default_admin_skips_existing_user(db_engine):
    """Does NOT promote an existing non-admin user with the same username."""
    factory = _factory(db_engine)

    # Pre-create a regular user with the target username
    async with factory() as db:
        user = User(username="admin", role="user", is_active=True)
        db.add(user)
        await db.commit()

    with patch("app.infra.init_admin.settings", _make_settings(
        default_admin_username="admin",
        default_admin_password="pass",
    )):
        await ensure_default_admin(factory)

    async with factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one()
        assert user.role == "user"  # NOT promoted

    assert await _count_users(factory) == 1


async def test_ensure_default_admin_without_password(db_engine):
    """User created with password_hash=None when no password configured."""
    factory = _factory(db_engine)

    with patch("app.infra.init_admin.settings", _make_settings(
        default_admin_username="admin",
    )):
        await ensure_default_admin(factory)

    async with factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one()
        assert user.password_hash is None
        assert user.api_key_hash is not None


async def test_ensure_default_admin_with_email(db_engine):
    """Email is stored when configured."""
    factory = _factory(db_engine)

    with patch("app.infra.init_admin.settings", _make_settings(
        default_admin_username="admin",
        default_admin_password="pass",
        default_admin_email="test@example.com",
    )):
        await ensure_default_admin(factory)

    async with factory() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one()
        assert user.email == "test@example.com"


async def test_ensure_default_admin_logs_api_key(db_engine, caplog):
    """API key appears in log output on creation."""
    factory = _factory(db_engine)

    with (
        patch("app.infra.init_admin.settings", _make_settings(
            default_admin_username="admin",
            default_admin_password="pass",
        )),
        caplog.at_level("INFO", logger="dg-core.init_admin"),
    ):
        await ensure_default_admin(factory)

    assert "DEFAULT ADMIN USER CREATED" in caplog.text
    assert "API Key" in caplog.text
    assert "will NOT be shown again" in caplog.text
