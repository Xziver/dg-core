"""Tests for the authentication system."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "display_name": "NewUser",
        "platform": "qq",
        "platform_uid": "qq_12345",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "api_key" in data
    assert "access_token" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_platform(client: AsyncClient):
    await register_user(client, "First", "qq", "dup_001")
    resp = await client.post("/api/auth/register", json={
        "display_name": "Second",
        "platform": "qq",
        "platform_uid": "dup_001",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_by_platform(client: AsyncClient):
    await register_user(client, "PlatformUser", "qq", "login_001")
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "qq",
        "platform_uid": "login_001",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_login_by_api_key(client: AsyncClient):
    user = await register_user(client, "ApiKeyUser", "web", "ak_001")
    resp = await client.post("/api/auth/login/api-key", json={
        "api_key": user["api_key"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user["user_id"]
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_invalid_platform(client: AsyncClient):
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "qq",
        "platform_uid": "nonexistent",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_login_invalid_api_key(client: AsyncClient):
    resp = await client.post("/api/auth/login/api-key", json={
        "api_key": "0" * 64,
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bind_platform(client: AsyncClient):
    user = await register_user(client, "BindUser", "qq", "bind_001")
    resp = await client.post("/api/auth/bind-platform", json={
        "platform": "discord",
        "platform_uid": "disc_001",
    }, headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["platform"] == "discord"
    assert resp.json()["status"] == "bound"


@pytest.mark.asyncio
async def test_bind_duplicate_platform(client: AsyncClient):
    user = await register_user(client, "BindDup", "qq", "bindd_001")
    await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "disc_dup",
    }, headers=user["headers"])

    resp = await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "disc_dup",
    }, headers=user["headers"])
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    user = await register_user(client, "MeUser", "qq", "me_001")
    resp = await client.get("/api/auth/me", headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user["user_id"]
    assert data["display_name"] == "MeUser"
    assert len(data["platform_bindings"]) == 1
    assert data["platform_bindings"][0]["platform"] == "qq"


@pytest.mark.asyncio
async def test_multi_platform_same_user(client: AsyncClient):
    user = await register_user(client, "MultiPlat", "qq", "multi_001")
    await client.post("/api/auth/bind-platform", json={
        "platform": "discord", "platform_uid": "multi_disc",
    }, headers=user["headers"])

    # Login via discord should return the same user
    resp = await client.post("/api/auth/login/platform", json={
        "platform": "discord", "platform_uid": "multi_disc",
    })
    assert resp.status_code == 200
    assert resp.json()["user_id"] == user["user_id"]


@pytest.mark.asyncio
async def test_protected_endpoint_no_auth(client: AsyncClient):
    resp = await client.post("/api/admin/games", json={"name": "NoAuth"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_key_header_auth(client: AsyncClient):
    user = await register_user(client, "ApiKeyH", "test", "akh_001")
    # Use X-API-Key header instead of Bearer token
    resp = await client.post("/api/admin/games", json={
        "name": "ViaApiKey",
    }, headers={"X-API-Key": user["api_key"]})
    assert resp.status_code == 200
    assert resp.json()["name"] == "ViaApiKey"
