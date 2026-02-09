"""Timeline — append and query event records."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import TimelineEvent
from app.modules.memory.short_term import short_term_memory


async def _next_seq(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(TimelineEvent.seq), 0)).where(
            TimelineEvent.session_id == session_id
        )
    )
    return result.scalar_one() + 1


async def append_event(
    db: AsyncSession,
    session_id: str,
    event_type: str,
    actor_id: str | None = None,
    data: dict | None = None,
    result_data: dict | None = None,
    narrative: str | None = None,
) -> TimelineEvent:
    seq = await _next_seq(db, session_id)
    event = TimelineEvent(
        session_id=session_id,
        seq=seq,
        event_type=event_type,
        actor_id=actor_id,
        data_json=json.dumps(data) if data else None,
        result_json=json.dumps(result_data) if result_data else None,
        narrative=narrative,
    )
    db.add(event)
    await db.flush()

    # Also push to short-term memory
    summary = f"{event_type}"
    if narrative:
        summary += f" — {narrative[:80]}"
    short_term_memory.add(session_id, seq, event_type, summary)

    return event


async def get_timeline(
    db: AsyncSession,
    session_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[TimelineEvent]:
    result = await db.execute(
        select(TimelineEvent)
        .where(TimelineEvent.session_id == session_id)
        .order_by(TimelineEvent.seq)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
