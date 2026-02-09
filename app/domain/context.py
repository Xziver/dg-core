"""Context assembly — build LLM context from current session state."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, world
from app.modules.memory.short_term import short_term_memory


async def build_context(
    db: AsyncSession,
    session_id: str,
    extra: dict | None = None,
) -> dict:
    """Assemble context dict for LLM prompt rendering."""
    ws = await world.get_world_state(db, session_id)
    ghosts = await character.get_ghosts_in_session(db, session_id)
    recent_text = short_term_memory.get_context_text(session_id)

    characters_info = []
    for g in ghosts:
        cmyk = character.get_cmyk(g)
        characters_info.append(
            f"{g.name}（HP: {g.hp}/{g.hp_max}, C={cmyk['C']} M={cmyk['M']} Y={cmyk['Y']} K={cmyk['K']}）"
        )

    ctx = {
        "sector_name": ws.current_sector if ws else "未知",
        "sector_features": "",
        "current_state": recent_text,
        "characters": "、".join(characters_info) if characters_info else "无",
        "recent_events": recent_text,
    }
    if extra:
        ctx.update(extra)
    return ctx
