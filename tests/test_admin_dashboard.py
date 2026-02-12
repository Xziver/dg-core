"""Tests for the admin dashboard UI."""

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture
def test_client():
    return TestClient(app, raise_server_exceptions=False)


# --- Page load tests (no DB required) ---


def test_admin_login_page_loads(test_client):
    """The admin login page should render without authentication."""
    resp = test_client.get("/admin/login")
    assert resp.status_code == 200
    assert "login" in resp.text.lower() or "password" in resp.text.lower()


def test_admin_unauthenticated_redirects_to_login(test_client):
    """Accessing /admin/ without auth should redirect to /admin/login."""
    resp = test_client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/admin/login" in resp.headers.get("location", "")


def test_admin_model_list_redirects_without_auth(test_client):
    """Accessing model list views without auth should redirect to login."""
    resp = test_client.get("/admin/user/list", follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_admin_dashboard_redirects_without_auth(test_client):
    """Accessing custom dashboard without auth should redirect to login."""
    resp = test_client.get("/admin/dashboard", follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_admin_cmyk_editor_redirects_without_auth(test_client):
    """Accessing CMYK editor without auth should redirect to login."""
    resp = test_client.get("/admin/cmyk-editor", follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_admin_bulk_redirects_without_auth(test_client):
    """Accessing bulk operations without auth should redirect to login."""
    resp = test_client.get("/admin/bulk", follow_redirects=False)
    assert resp.status_code in (302, 303)


# --- Login tests (mock DB) ---


def _make_mock_user(user_id="admin-001", role="admin", is_active=True, api_key="test-key-123"):
    """Create a mock User object."""
    mock_user = type("User", (), {
        "id": user_id,
        "username": "Admin",
        "role": role,
        "is_active": is_active,
        "api_key_hash": hashlib.sha256(api_key.encode()).hexdigest(),
        "password_hash": None,
    })()
    return mock_user


def _mock_scalar_result(user):
    """Create a mock DB result that returns user from scalar_one_or_none."""
    mock_result = type("Result", (), {"scalar_one_or_none": lambda self: user})()
    return mock_result


@patch("app.admin.auth.async_session_factory")
def test_admin_login_rejects_non_admin(mock_factory, test_client):
    """Login should fail for non-admin users."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_mock_scalar_result(None))
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_factory.return_value = mock_db

    resp = test_client.post(
        "/admin/login",
        data={"username": "anyone", "password": "wrong-key"},
        follow_redirects=False,
    )
    # After failed login, sqladmin returns 400 Bad Request
    assert resp.status_code == 400


@patch("app.admin.auth.async_session_factory")
def test_admin_login_accepts_admin_user(mock_factory, test_client):
    """Login should succeed for admin users with correct API key."""
    api_key = "valid-admin-key-123"
    user = _make_mock_user(role="admin", api_key=api_key)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_mock_scalar_result(user))
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_factory.return_value = mock_db

    resp = test_client.post(
        "/admin/login",
        data={"username": "admin", "password": api_key},
        follow_redirects=False,
    )
    # Successful login redirects to admin index
    assert resp.status_code in (302, 303)
    location = resp.headers.get("location", "")
    assert "/admin" in location
    # Should not redirect back to login
    assert "/admin/login" not in location


@patch("app.admin.auth.async_session_factory")
def test_admin_login_rejects_empty_password(mock_factory, test_client):
    """Login should fail with empty password."""
    resp = test_client.post(
        "/admin/login",
        data={"username": "admin", "password": ""},
        follow_redirects=False,
    )
    # sqladmin returns 400 for failed login
    assert resp.status_code == 400
    # Factory should not have been called since we short-circuit on empty key
    mock_factory.assert_not_called()
