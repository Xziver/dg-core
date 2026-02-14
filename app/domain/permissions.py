"""Permission helpers — DM/PL role checks for game operations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import GamePlayer


async def require_dm(
    db: AsyncSession, game_id: str, user_id: str
) -> GamePlayer:
    """Verify user is DM in this game. Raises ValueError if not."""
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = result.scalar_one_or_none()
    if gp is None:
        raise ValueError(f"User {user_id} is not in game {game_id}")
    if gp.role != "DM":
        raise ValueError("Only DM can perform this action")
    return gp


async def require_game_player(
    db: AsyncSession, game_id: str, user_id: str
) -> GamePlayer:
    """Verify user is in the game (any role). Raises ValueError if not."""
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = result.scalar_one_or_none()
    if gp is None:
        raise ValueError(f"User {user_id} is not in game {game_id}")
    return gp
