"""Session management — create, join, end sessions."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Player, Session, SessionPlayer, WorldState


async def create_session(
    db: AsyncSession,
    name: str,
    created_by: str,
    config: dict | None = None,
) -> Session:
    session = Session(
        name=name,
        created_by=created_by,
        config_json=json.dumps(config) if config else None,
    )
    db.add(session)
    await db.flush()

    # Creator auto-joins as KP
    link = SessionPlayer(session_id=session.id, player_id=created_by, role="KP")
    db.add(link)

    # Initialize world state
    world = WorldState(
        session_id=session.id,
        global_flags_json=json.dumps({}),
    )
    db.add(world)
    await db.flush()
    return session


async def join_session(
    db: AsyncSession,
    session_id: str,
    player_id: str,
    role: str = "PL",
) -> SessionPlayer:
    link = SessionPlayer(session_id=session_id, player_id=player_id, role=role)
    db.add(link)
    await db.flush()
    return link


async def get_session(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_session_players(db: AsyncSession, session_id: str) -> list[SessionPlayer]:
    result = await db.execute(
        select(SessionPlayer).where(SessionPlayer.session_id == session_id)
    )
    return list(result.scalars().all())


async def start_session(db: AsyncSession, session_id: str) -> Session:
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    session.status = "active"
    await db.flush()
    return session


async def end_session(db: AsyncSession, session_id: str) -> Session:
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    session.status = "ended"
    await db.flush()
    return session
