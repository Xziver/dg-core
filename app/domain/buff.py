"""Buff/debuff management — add, remove, list, tick, apply during checks."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Buff


def classify_expression(expression: str) -> str:
    """Classify a buff expression into its type.

    Returns: "numeric", "dice", "attribute", or "text"
    """
    expr = expression.strip()
    # Numeric: pure +N or -N or just a number
    if re.match(r"^[+-]?\d+$", expr):
        return "numeric"
    # Attribute: starts with c/m/y/k letter optionally followed by +/- number
    if re.match(r"^[cmykCMYK]\s*([+-]\s*\d+)?$", expr):
        return "attribute"
    # Dice: contains NdM pattern
    if re.match(r".*\d*d\d+.*", expr, re.IGNORECASE):
        return "dice"
    # Everything else is text
    return "text"


async def add_buff(
    db: AsyncSession,
    ghost_id: str,
    game_id: str,
    name: str,
    expression: str,
    remaining_rounds: int = 1,
    created_by: str = "",
) -> Buff:
    """Add a buff/debuff to a ghost."""
    buff_type = classify_expression(expression)
    buff = Buff(
        ghost_id=ghost_id,
        game_id=game_id,
        name=name,
        expression=expression,
        buff_type=buff_type,
        remaining_rounds=remaining_rounds,
        created_by=created_by,
    )
    db.add(buff)
    await db.flush()
    return buff


async def remove_buff(db: AsyncSession, buff_id: str) -> None:
    """Remove a buff by ID."""
    result = await db.execute(select(Buff).where(Buff.id == buff_id))
    buff = result.scalar_one_or_none()
    if buff is None:
        raise ValueError(f"Buff {buff_id} not found")
    await db.delete(buff)
    await db.flush()


async def remove_buff_by_name(
    db: AsyncSession, ghost_id: str, name: str
) -> None:
    """Remove a buff by ghost and name."""
    result = await db.execute(
        select(Buff).where(Buff.ghost_id == ghost_id, Buff.name == name)
    )
    buff = result.scalar_one_or_none()
    if buff is None:
        raise ValueError(f"Buff '{name}' not found on ghost {ghost_id}")
    await db.delete(buff)
    await db.flush()


async def get_buffs(db: AsyncSession, ghost_id: str) -> list[Buff]:
    """Get all active buffs for a ghost."""
    result = await db.execute(select(Buff).where(Buff.ghost_id == ghost_id))
    return list(result.scalars().all())


async def tick_buffs(db: AsyncSession, ghost_id: str) -> list[str]:
    """Tick all non-permanent buffs (decrement remaining_rounds).

    Removes expired buffs. Returns list of expired buff names.
    Called on each event check / reroll.
    """
    buffs = await get_buffs(db, ghost_id)
    expired = []
    for buff in buffs:
        if buff.remaining_rounds == -1:
            continue  # Permanent
        buff.remaining_rounds -= 1
        if buff.remaining_rounds <= 0:
            expired.append(buff.name)
            await db.delete(buff)
    await db.flush()
    return expired


def compute_buff_modifier(
    buffs: list[Buff],
    cmyk_values: dict[str, int],
    default_dice_sides: int = 6,
) -> tuple[dict[str, int], int]:
    """Compute buff effects for an event check.

    Returns:
        (cmyk_adjustments, flat_modifier)
        - cmyk_adjustments: {"C": +2, "M": -1, ...} adjustments to effective CMYK
        - flat_modifier: Total flat bonus/penalty to add to roll total
    """
    from app.modules.dice.parser import roll_expression

    cmyk_adj: dict[str, int] = {"C": 0, "M": 0, "Y": 0, "K": 0}
    flat_mod = 0

    for buff in buffs:
        if buff.buff_type == "text":
            continue
        elif buff.buff_type == "numeric":
            flat_mod += int(buff.expression)
        elif buff.buff_type == "attribute":
            expr = buff.expression.strip()
            color = expr[0].upper()
            if len(expr) > 1:
                mod = int(expr[1:].replace(" ", ""))
            else:
                mod = 1
            cmyk_adj[color] = cmyk_adj.get(color, 0) + mod
        elif buff.buff_type == "dice":
            result = roll_expression(buff.expression, cmyk_values, default_dice_sides)
            flat_mod += result.total

    return cmyk_adj, flat_mod
