"""Integration tests for the admin and bot API endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine"] == "dg-core"


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "username": "TestPlayer",
        "platform": "discord",
        "platform_uid": "user123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "api_key" in data
    assert "access_token" in data
    assert len(data["api_key"]) == 64


@pytest.mark.asyncio
async def test_create_game(client: AsyncClient):
    user = await register_user(client, "KP", "discord", "kp001")

    resp = await client.post("/api/admin/games", json={
        "name": "Test Game",
    }, headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Game"
    assert data["status"] == "preparing"


@pytest.mark.asyncio
async def test_create_patient_and_ghost(client: AsyncClient):
    user1 = await register_user(client, "Player1", "discord", "pl001")
    user2 = await register_user(client, "Player2", "discord", "pl002")

    game_resp = await client.post("/api/admin/games", json={
        "name": "CharTest",
    }, headers=user1["headers"])
    game_id = game_resp.json()["game_id"]

    # Create patient
    patient_resp = await client.post("/api/admin/characters/patient", json={
        "user_id": user1["user_id"],
        "game_id": game_id,
        "name": "测试患者",
        "soul_color": "C",
        "gender": "男",
        "age": 25,
        "personality_archives": {
            "C": "一个关于忧郁的故事",
            "M": "一个关于愤怒的故事",
        },
        "ideal_projection": "我想成为一个自由的旅人",
    }, headers=user1["headers"])
    assert patient_resp.status_code == 200
    patient_data = patient_resp.json()
    assert patient_data["name"] == "测试患者"
    assert patient_data["swap_file"]["soul_color"] == "C"
    assert "C" in patient_data["swap_file"]["revealed_archive"]
    assert "M" not in patient_data["swap_file"]["revealed_archive"]

    # Create ghost
    ghost_resp = await client.post("/api/admin/characters/ghost", json={
        "patient_id": patient_data["patient_id"],
        "creator_user_id": user2["user_id"],
        "game_id": game_id,
        "name": "测试幽灵",
        "soul_color": "C",
        "appearance": "数字蓝色光影形态",
        "personality": "冷静分析型",
        "print_abilities": [
            {"name": "逆流之雨", "color": "C", "description": "创造倒流的数据雨", "ability_count": 2},
        ],
    }, headers=user2["headers"])
    assert ghost_resp.status_code == 200
    ghost_data = ghost_resp.json()
    assert ghost_data["cmyk"]["C"] == 1
    assert ghost_data["cmyk"]["M"] == 0
    assert ghost_data["hp"] == 10
    assert len(ghost_data["print_abilities"]) == 1
    assert ghost_data["print_abilities"][0]["name"] == "逆流之雨"


@pytest.mark.asyncio
async def test_get_character(client: AsyncClient):
    user = await register_user(client, "P1", "web", "u1")
    h = user["headers"]

    g = await client.post("/api/admin/games", json={"name": "G1"}, headers=h)
    gid = g.json()["game_id"]
    pat = await client.post("/api/admin/characters/patient", json={
        "user_id": user["user_id"], "game_id": gid, "name": "患者A", "soul_color": "M",
    }, headers=h)
    patient_id = pat.json()["patient_id"]

    resp = await client.get(f"/api/admin/characters/{patient_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["type"] == "patient"
    assert resp.json()["name"] == "患者A"


@pytest.mark.asyncio
async def test_game_not_found(client: AsyncClient):
    user = await register_user(client, "U", "test", "nf1")
    resp = await client.get("/api/bot/games/nonexistent", headers=user["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_request(client: AsyncClient):
    resp = await client.post("/api/admin/games", json={"name": "Nope"})
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_region_crud(client: AsyncClient):
    user = await register_user(client, "RegionKP", "qq", "r1")
    h = user["headers"]

    g = await client.post("/api/admin/games", json={"name": "RegionTest"}, headers=h)
    game_id = g.json()["game_id"]

    r1 = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "A", "name": "数据荒原",
    }, headers=h)
    assert r1.status_code == 200
    assert r1.json()["code"] == "A"

    r2 = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "B", "name": "信号塔区",
    }, headers=h)
    assert r2.status_code == 200

    regions = await client.get(f"/api/admin/games/{game_id}/regions", headers=h)
    assert regions.status_code == 200
    assert len(regions.json()["regions"]) == 2

    region_a_id = r1.json()["region_id"]
    loc = await client.post(f"/api/admin/regions/{region_a_id}/locations", json={
        "name": "数据废墟",
        "description": "一片荒废的数据存储设施",
        "content": "这里曾经是灰山城最大的数据中心...",
    }, headers=h)
    assert loc.status_code == 200
    assert loc.json()["name"] == "数据废墟"

    locs = await client.get(f"/api/admin/regions/{region_a_id}/locations", headers=h)
    assert locs.status_code == 200
    assert len(locs.json()["locations"]) == 1
