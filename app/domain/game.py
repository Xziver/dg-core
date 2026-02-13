"""Game management — create, join, start, end games."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Game, GamePlayer, Patient, Session


async def create_game(
    db: AsyncSession,
    name: str,
    created_by: str,
    config: dict | None = None,
) -> Game:
    game = Game(
        name=name,
        created_by=created_by,
        config_json=json.dumps(config) if config else None,
        flags_json=json.dumps({}),
    )
    db.add(game)
    await db.flush()

    # Creator auto-joins as KP
    link = GamePlayer(game_id=game.id, user_id=created_by, role="KP")
    db.add(link)
    await db.flush()
    return game


async def join_game(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    role: str = "PL",
) -> GamePlayer:
    link = GamePlayer(game_id=game_id, user_id=user_id, role=role)
    db.add(link)
    await db.flush()
    return link


async def get_game(db: AsyncSession, game_id: str) -> Game | None:
    result = await db.execute(select(Game).where(Game.id == game_id))
    return result.scalar_one_or_none()


async def get_game_players(db: AsyncSession, game_id: str) -> list[GamePlayer]:
    result = await db.execute(
        select(GamePlayer).where(GamePlayer.game_id == game_id)
    )
    return list(result.scalars().all())


async def start_game(db: AsyncSession, game_id: str) -> Game:
    game = await get_game(db, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    game.status = "active"
    await db.flush()
    return game


async def end_game(db: AsyncSession, game_id: str) -> Game:
    game = await get_game(db, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    game.status = "ended"
    await db.flush()
    return game


async def get_flags(db: AsyncSession, game_id: str) -> dict:
    game = await get_game(db, game_id)
    if game is None:
        return {}
    return json.loads(game.flags_json) if game.flags_json else {}


async def set_flag(
    db: AsyncSession, game_id: str, key: str, value: object
) -> dict:
    game = await get_game(db, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    flags = json.loads(game.flags_json) if game.flags_json else {}
    flags[key] = value
    game.flags_json = json.dumps(flags)
    await db.flush()
    return flags


async def switch_character(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    patient_id: str,
) -> GamePlayer:
    """Switch a player's active character. PL only, no active session allowed."""
    # Find the GamePlayer link
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = result.scalar_one_or_none()
    if gp is None:
        raise ValueError(f"Player {user_id} not found in game {game_id}")
    if gp.role != "PL":
        raise ValueError("Only PL players can set an active character")

    # Verify the patient belongs to this user and game
    patient_result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.user_id == user_id,
            Patient.game_id == game_id,
        )
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise ValueError(
            f"Patient {patient_id} not found for user {user_id} in game {game_id}"
        )

    # Reject if there's an active session in this game
    active_session = await db.execute(
        select(Session).where(
            Session.game_id == game_id,
            Session.status == "active",
        )
    )
    if active_session.scalar_one_or_none() is not None:
        raise ValueError("Cannot switch character during an active session")

    gp.active_patient_id = patient_id
    await db.flush()
    return gp
