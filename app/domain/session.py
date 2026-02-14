"""Session management — play session lifecycle (start/end/pause/resume within a game)."""

from __future__ import annotations

from datetime import timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Patient, Session, SessionPlayer


async def start_session(
    db: AsyncSession,
    game_id: str,
    started_by: str,
    region_id: str | None = None,
    location_id: str | None = None,
) -> Session:
    """Start a new play session within a game."""
    session = Session(
        game_id=game_id,
        started_by=started_by,
        region_id=region_id,
        location_id=location_id,
        status="active",
    )
    db.add(session)
    await db.flush()

    # Auto-join players at session's location/region
    await auto_join_location_players(db, session)

    return session


async def end_session(db: AsyncSession, session_id: str) -> Session:
    """End a play session."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    if session.status == "ended":
        raise ValueError("Session is already ended")
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return session


async def pause_session(db: AsyncSession, session_id: str) -> Session:
    """Pause an active session."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    if session.status != "active":
        raise ValueError(f"Cannot pause session with status '{session.status}'")
    session.status = "paused"
    await db.flush()
    return session


async def resume_session(db: AsyncSession, session_id: str) -> Session:
    """Resume a paused session."""
    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    if session.status != "paused":
        raise ValueError(f"Cannot resume session with status '{session.status}'")
    session.status = "active"
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


# --- Session player management ---


async def add_player_to_session(
    db: AsyncSession, session_id: str, patient_id: str
) -> SessionPlayer:
    """Add a patient to a session. Validates no duplicate."""
    existing = await db.execute(
        select(SessionPlayer).where(
            SessionPlayer.session_id == session_id,
            SessionPlayer.patient_id == patient_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Patient is already in this session")

    sp = SessionPlayer(session_id=session_id, patient_id=patient_id)
    db.add(sp)
    await db.flush()
    return sp


async def remove_player_from_session(
    db: AsyncSession, session_id: str, patient_id: str
) -> None:
    """Remove a patient from a session."""
    result = await db.execute(
        select(SessionPlayer).where(
            SessionPlayer.session_id == session_id,
            SessionPlayer.patient_id == patient_id,
        )
    )
    sp = result.scalar_one_or_none()
    if sp is None:
        raise ValueError("Patient is not in this session")
    await db.delete(sp)
    await db.flush()


async def get_session_players(
    db: AsyncSession, session_id: str
) -> list[SessionPlayer]:
    """Get all players in a session."""
    result = await db.execute(
        select(SessionPlayer).where(SessionPlayer.session_id == session_id)
    )
    return list(result.scalars().all())


async def auto_join_location_players(
    db: AsyncSession, session: Session
) -> list[SessionPlayer]:
    """Auto-join patients at the session's location or region."""
    joined: list[SessionPlayer] = []

    if session.location_id:
        patients_result = await db.execute(
            select(Patient).where(
                Patient.game_id == session.game_id,
                Patient.current_location_id == session.location_id,
            )
        )
    elif session.region_id:
        patients_result = await db.execute(
            select(Patient).where(
                Patient.game_id == session.game_id,
                Patient.current_region_id == session.region_id,
            )
        )
    else:
        return joined

    patients = list(patients_result.scalars().all())
    for patient in patients:
        existing = await db.execute(
            select(SessionPlayer).where(
                SessionPlayer.session_id == session.id,
                SessionPlayer.patient_id == patient.id,
            )
        )
        if existing.scalar_one_or_none() is None:
            sp = SessionPlayer(session_id=session.id, patient_id=patient.id)
            db.add(sp)
            joined.append(sp)

    if joined:
        await db.flush()
    return joined


async def get_session_info(db: AsyncSession, session_id: str) -> dict:
    """Get comprehensive session info including players and active events."""
    from app.domain.rules import event_check

    session = await get_session(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")

    players = await get_session_players(db, session_id)
    active_events = await event_check.get_active_events(db, session_id)

    return {
        "session_id": session.id,
        "game_id": session.game_id,
        "status": session.status,
        "region_id": session.region_id,
        "location_id": session.location_id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "players": [
            {"patient_id": sp.patient_id, "joined_at": sp.joined_at.isoformat()}
            for sp in players
        ],
        "active_events": [
            {
                "id": e.id,
                "name": e.name,
                "expression": e.expression,
                "color_restriction": e.color_restriction,
            }
            for e in active_events
        ],
    }
