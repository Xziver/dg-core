"""End-to-end scenario test: full game flow via API."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


@pytest.mark.asyncio
async def test_full_game_flow(client: AsyncClient):
    """
    End-to-end scenario:
    1. Register KP and PL users
    2. Create a game (KP)
    3. PL joins game
    4. Create regions
    5. Create patient + ghost for PL
    6. Start game
    7. Start play session
    8. Submit skill_check event
    9. Submit attack event
    10. Query timeline
    11. End session + end game
    """

    # 1. Register users
    kp = await register_user(client, "KP小倩", "discord", "kp_main")
    pl = await register_user(client, "玩家A", "discord", "pl_main")
    pl2 = await register_user(client, "玩家B", "discord", "pl_ghost_creator")

    kp_h = kp["headers"]
    pl_h = pl["headers"]

    # 2. Create game
    game_resp = await client.post("/api/admin/games", json={
        "name": "灰山城第一章·信号裂痕",
        "config": {"dice_type": 6, "initial_hp": 10},
    }, headers=kp_h)
    game_id = game_resp.json()["game_id"]

    # 3. PL joins game
    join_resp = await client.post(f"/api/admin/games/{game_id}/players", json={
        "user_id": pl["user_id"], "role": "PL",
    }, headers=kp_h)
    assert join_resp.status_code == 200

    await client.post(f"/api/admin/games/{game_id}/players", json={
        "user_id": pl2["user_id"], "role": "PL",
    }, headers=kp_h)

    # 4. Create regions
    region_resp = await client.post(f"/api/admin/games/{game_id}/regions", json={
        "code": "A", "name": "数据荒原",
    }, headers=kp_h)
    assert region_resp.status_code == 200

    # 5. Create patient + ghost
    patient_resp = await client.post("/api/admin/characters/patient", json={
        "user_id": pl["user_id"],
        "game_id": game_id,
        "name": "林默",
        "soul_color": "C",
        "gender": "男",
        "age": 28,
        "identity": "前数据分析师",
        "personality_archives": {
            "C": "我总是在深夜思考，那些数据背后是否隐藏着什么",
            "M": "那天我在暴雨中狂奔，仿佛要甩掉所有枷锁",
            "Y": "和朋友们在天台看日落，那一刻什么都不用想",
            "K": "即使全世界都说不可能，我也要找到那个答案",
        },
        "ideal_projection": "我想成为一个能看穿一切谎言的存在，一个数据世界的守望者",
    }, headers=pl_h)
    patient_id = patient_resp.json()["patient_id"]
    swap = patient_resp.json()["swap_file"]
    assert swap["soul_color"] == "C"

    ghost_resp = await client.post("/api/admin/characters/ghost", json={
        "patient_id": patient_id,
        "creator_user_id": pl2["user_id"],
        "game_id": game_id,
        "name": "Echo",
        "soul_color": "C",
        "appearance": "半透明的蓝色人形光影，周身环绕着飘浮的数据碎片",
        "personality": "冷静而好奇，经常用数据逻辑分析一切",
        "print_abilities": [
            {
                "name": "数据逆流",
                "color": "C",
                "description": "创造一道逆流的数据瀑布，暂时扭曲局部的因果逻辑",
                "ability_count": 2,
            },
        ],
    }, headers=pl2["headers"])
    ghost_id = ghost_resp.json()["ghost_id"]
    assert ghost_resp.json()["cmyk"]["C"] == 1

    # Also create a second patient+ghost as target
    p2_patient = await client.post("/api/admin/characters/patient", json={
        "user_id": pl2["user_id"], "game_id": game_id, "name": "敌方实体", "soul_color": "M",
    }, headers=pl2["headers"])
    target_patient_id = p2_patient.json()["patient_id"]

    target_ghost = await client.post("/api/admin/characters/ghost", json={
        "patient_id": target_patient_id,
        "creator_user_id": pl["user_id"],
        "game_id": game_id,
        "name": "Glitch",
        "soul_color": "M",
    }, headers=pl_h)
    target_ghost_id = target_ghost.json()["ghost_id"]

    # 6. Start game
    start_game_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "user_id": kp["user_id"],
        "payload": {"event_type": "game_start"},
    }, headers=kp_h)
    assert start_game_resp.status_code == 200
    assert start_game_resp.json()["success"] is True
    assert start_game_resp.json()["data"]["status"] == "active"

    # Verify game is active
    game_info = await client.get(f"/api/bot/games/{game_id}", headers=kp_h)
    assert game_info.json()["status"] == "active"

    # 7. Start play session
    session_start_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "user_id": kp["user_id"],
        "payload": {"event_type": "session_start"},
    }, headers=kp_h)
    assert session_start_resp.status_code == 200
    assert session_start_resp.json()["success"] is True
    session_id = session_start_resp.json()["data"]["session_id"]

    # 8. Skill check
    check_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "user_id": pl["user_id"],
        "payload": {
            "event_type": "skill_check",
            "color": "C",
            "difficulty": 3,
            "context": "尝试分析扇区的数据流，寻找异常信号",
        },
    }, headers=pl_h)
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["success"] is True
    assert check_data["event_type"] == "skill_check"
    assert "roll_total" in check_data["data"]
    assert "check_success" in check_data["data"]
    assert len(check_data["rolls"]) == 1

    # 9. Attack
    atk_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "user_id": pl["user_id"],
        "payload": {
            "event_type": "attack",
            "attacker_ghost_id": ghost_id,
            "target_ghost_id": target_ghost_id,
            "color_used": "C",
        },
    }, headers=pl_h)
    assert atk_resp.status_code == 200
    atk_data = atk_resp.json()
    assert atk_data["success"] is True
    assert atk_data["event_type"] == "attack"
    assert "hit" in atk_data["data"]

    # 10. Query timeline
    tl_resp = await client.get(
        f"/api/bot/sessions/{session_id}/timeline", headers=kp_h
    )
    assert tl_resp.status_code == 200
    events = tl_resp.json()["events"]
    assert len(events) >= 3  # session_start + skill_check + attack
    event_types = [e["event_type"] for e in events]
    assert "session_start" in event_types
    assert "skill_check" in event_types
    assert "attack" in event_types

    # 11. End session and game
    end_session_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "session_id": session_id,
        "user_id": kp["user_id"],
        "payload": {"event_type": "session_end"},
    }, headers=kp_h)
    assert end_session_resp.status_code == 200
    assert end_session_resp.json()["data"]["status"] == "ended"

    end_game_resp = await client.post("/api/bot/events", json={
        "game_id": game_id,
        "user_id": kp["user_id"],
        "payload": {"event_type": "game_end"},
    }, headers=kp_h)
    assert end_game_resp.status_code == 200
    assert end_game_resp.json()["data"]["status"] == "ended"
