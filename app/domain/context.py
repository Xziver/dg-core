"""Context assembly — build LLM context from current game state."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, region as region_mod
from app.modules.memory.short_term import short_term_memory


async def build_context(
    db: AsyncSession,
    game_id: str,
    session_id: str | None = None,
    user_id: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Assemble context dict for LLM prompt rendering."""
    ghosts = await character.get_ghosts_in_game(db, game_id)
    regions = await region_mod.get_regions(db, game_id)

    # Use session_id for short-term memory context if available
    memory_key = session_id or game_id
    recent_text = short_term_memory.get_context_text(memory_key)

    characters_info = []
    for g in ghosts:
        cmyk = character.get_cmyk(g)
        characters_info.append(
            f"{g.name}（HP: {g.hp}/{g.hp_max}, C={cmyk['C']} M={cmyk['M']} Y={cmyk['Y']} K={cmyk['K']}）"
        )

    region_names = "、".join(r.name for r in regions) if regions else "未知"

    ctx = {
        "region_names": region_names,
        "current_state": recent_text,
        "characters": "、".join(characters_info) if characters_info else "无",
        "recent_events": recent_text,
    }
    if extra:
        ctx.update(extra)
    return ctx
