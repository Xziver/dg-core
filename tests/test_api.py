"""Integration tests for the admin and bot API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["engine"] == "dg-core"


@pytest.mark.asyncio
async def test_create_player(client: AsyncClient):
    resp = await client.post("/api/admin/players", json={
        "platform": "discord",
        "platform_uid": "user123",
        "display_name": "TestPlayer",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "player_id" in data
    assert "api_key" in data
    assert len(data["api_key"]) == 64


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient):
    # Create a player first
    player_resp = await client.post("/api/admin/players", json={
        "platform": "discord",
        "platform_uid": "kp001",
        "display_name": "KP",
    })
    player_id = player_resp.json()["player_id"]

    # Create session
    resp = await client.post("/api/admin/sessions", json={
        "name": "Test Session",
        "created_by": player_id,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Session"
    assert data["status"] == "preparing"


@pytest.mark.asyncio
async def test_create_patient_and_ghost(client: AsyncClient):
    # Setup: player + session
    player_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl001", "display_name": "Player1",
    })
    player_id = player_resp.json()["player_id"]

    creator_resp = await client.post("/api/admin/players", json={
        "platform": "discord", "platform_uid": "pl002", "display_name": "Player2",
    })
    creator_id = creator_resp.json()["player_id"]

    session_resp = await client.post("/api/admin/sessions", json={
        "name": "CharTest", "created_by": player_id,
    })
    session_id = session_resp.json()["session_id"]

    # Create patient
    patient_resp = await client.post("/api/admin/characters/patient", json={
        "player_id": player_id,
        "session_id": session_id,
        "name": "测试患者",
        "soul_color": "C",
        "gender": "男",
        "age": 25,
        "personality_archives": {
            "C": "一个关于忧郁的故事",
            "M": "一个关于愤怒的故事",
        },
        "ideal_projection": "我想成为一个自由的旅人",
    })
    assert patient_resp.status_code == 200
    patient_data = patient_resp.json()
    assert patient_data["name"] == "测试患者"
    assert patient_data["swap_file"]["soul_color"] == "C"
    assert "C" in patient_data["swap_file"]["revealed_archive"]
    # SWAP should NOT reveal M archive
    assert "M" not in patient_data["swap_file"]["revealed_archive"]

    # Create ghost
    ghost_resp = await client.post("/api/admin/characters/ghost", json={
        "patient_id": patient_data["patient_id"],
        "creator_player_id": creator_id,
        "session_id": session_id,
        "name": "测试幽灵",
        "soul_color": "C",
        "appearance": "数字蓝色光影形态",
        "personality": "冷静分析型",
        "print_abilities": [
            {"name": "逆流之雨", "color": "C", "description": "创造倒流的数据雨", "ability_count": 2},
        ],
    })
    assert ghost_resp.status_code == 200
    ghost_data = ghost_resp.json()
    assert ghost_data["cmyk"]["C"] == 1
    assert ghost_data["cmyk"]["M"] == 0
    assert ghost_data["hp"] == 10
    assert len(ghost_data["print_abilities"]) == 1
    assert ghost_data["print_abilities"][0]["name"] == "逆流之雨"


@pytest.mark.asyncio
async def test_get_character(client: AsyncClient):
    # Create player + session + patient
    p = await client.post("/api/admin/players", json={
        "platform": "web", "platform_uid": "u1", "display_name": "P1"
    })
    pid = p.json()["player_id"]
    s = await client.post("/api/admin/sessions", json={"name": "S1", "created_by": pid})
    sid = s.json()["session_id"]
    pat = await client.post("/api/admin/characters/patient", json={
        "player_id": pid, "session_id": sid, "name": "患者A", "soul_color": "M",
    })
    patient_id = pat.json()["patient_id"]

    # Lookup patient
    resp = await client.get(f"/api/admin/characters/{patient_id}")
    assert resp.status_code == 200
    assert resp.json()["type"] == "patient"
    assert resp.json()["name"] == "患者A"


@pytest.mark.asyncio
async def test_session_not_found(client: AsyncClient):
    resp = await client.get("/api/bot/sessions/nonexistent")
    assert resp.status_code == 404
