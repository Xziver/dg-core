"""Session management — play session lifecycle (start/end within a game)."""

from __future__ import annotations

from datetime import timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Session


async def start_session(
    db: AsyncSession,
    game_id: str,
    started_by: str,
    region_id: str | None = None,
) -> Session:
    """Start a new play session within a game."""
    session = Session(
        game_id=game_id,
        started_by=started_by,
        region_id=region_id,
        status="active",
    )
    db.add(session)
    await db.flush()
    return session


async def end_session(db: AsyncSession, session_id: str) -> Session:
    """End a play session."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def get_session(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_active_session(
    db: AsyncSession,
    game_id: str,
    region_id: str | None = None,
) -> Session | None:
    """Find the currently active session for a game, optionally in a specific region."""
    stmt = select(Session).where(
        Session.game_id == game_id,
        Session.status == "active",
    )
    if region_id is not None:
        stmt = stmt.where(Session.region_id == region_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_game_sessions(
    db: AsyncSession,
    game_id: str,
    limit: int = 50,
) -> list[Session]:
    result = await db.execute(
        select(Session)
        .where(Session.game_id == game_id)
        .order_by(Session.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
