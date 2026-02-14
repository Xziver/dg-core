"""Event check system — DM-set events, player checks, rerolls."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import buff as buff_mod, character, timeline
from app.infra.config import settings
from app.models.db_models import (
    EventAbilityUsage,
    EventDefinition,
    Ghost,
    Patient,
)
from app.models.result import EngineResult, StateChange
from app.modules.dice.parser import roll_expression


# --- Event definition management (direct API, not dispatcher) ---


async def set_event(
    db: AsyncSession,
    session_id: str,
    game_id: str,
    name: str,
    expression: str,
    color_restriction: str | None = None,
    created_by: str = "",
) -> EventDefinition:
    """DM creates/replaces an event definition for the current session."""
    # Deactivate any existing active event with the same name
    existing = await get_active_event(db, session_id, name)
    if existing is not None:
        existing.is_active = False

    event_def = EventDefinition(
        session_id=session_id,
        game_id=game_id,
        name=name,
        expression=expression,
        color_restriction=color_restriction.upper() if color_restriction else None,
        created_by=created_by,
    )
    db.add(event_def)
    await db.flush()
    return event_def


async def get_active_event(
    db: AsyncSession, session_id: str, event_name: str
) -> EventDefinition | None:
    result = await db.execute(
        select(EventDefinition).where(
            EventDefinition.session_id == session_id,
            EventDefinition.name == event_name,
            EventDefinition.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_active_events(
    db: AsyncSession, session_id: str
) -> list[EventDefinition]:
    result = await db.execute(
        select(EventDefinition).where(
            EventDefinition.session_id == session_id,
            EventDefinition.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


async def deactivate_event(
    db: AsyncSession, session_id: str, event_name: str
) -> EventDefinition:
    event_def = await get_active_event(db, session_id, event_name)
    if event_def is None:
        raise ValueError(f"No active event '{event_name}' in session")
    event_def.is_active = False
    await db.flush()
    return event_def


async def deactivate_event_by_id(
    db: AsyncSession, event_def_id: str
) -> EventDefinition:
    result = await db.execute(
        select(EventDefinition).where(EventDefinition.id == event_def_id)
    )
    event_def = result.scalar_one_or_none()
    if event_def is None:
        raise ValueError(f"Event definition {event_def_id} not found")
    event_def.is_active = False
    await db.flush()
    return event_def


# --- Event check (dispatcher) ---


async def handle_event_check(
    db: AsyncSession,
    game_id: str,
    session_id: str,
    user_id: str,
    ghost: Ghost,
    patient: Patient,
    event_name: str,
    color: str | None = None,
) -> EngineResult:
    """Player performs an event check against a DM-set event.

    Flow:
    1. Find active EventDefinition by name
    2. Determine color: event color_restriction > player choice > patient soul_color
    3. Get CMYK + buff adjustments → effective dice count
    4. Roll player: {effective}d{sides} + flat modifiers
    5. Roll target (first check only): evaluate DM expression, cache result
    6. Compare totals
    7. Tick buffs
    8. Record timeline
    """
    event_def = await get_active_event(db, session_id, event_name)
    if event_def is None:
        return EngineResult(
            success=False, event_type="event_check",
            error=f"No active event '{event_name}' in this session",
        )

    # Determine check color
    check_color = _resolve_color(event_def, color, patient)

    # Get CMYK values and apply buff adjustments
    cmyk = character.get_cmyk(ghost)
    buffs = await buff_mod.get_buffs(db, ghost.id)
    cmyk_adj, flat_mod = buff_mod.compute_buff_modifier(
        buffs, cmyk, settings.default_dice_type
    )

    effective_value = cmyk.get(check_color, 0) + cmyk_adj.get(check_color, 0)
    effective_value = max(0, effective_value)

    # Roll player dice
    player_roll = roll_expression(
        f"{effective_value}d{settings.default_dice_type}"
    )
    player_total = player_roll.total + flat_mod

    # Roll target (first check uses DM expression, subsequent reuse cached)
    if event_def.target_roll_total is None:
        target_roll = roll_expression(
            event_def.expression, cmyk, settings.default_dice_type
        )
        event_def.target_roll_total = target_roll.total
        event_def.target_roll_detail = json.dumps({
            "expression": target_roll.expression,
            "rolls": target_roll.individual_rolls,
            "total": target_roll.total,
        })
    target_total = event_def.target_roll_total

    check_success = player_total >= target_total

    # Tick buffs
    expired = await buff_mod.tick_buffs(db, ghost.id)

    # Record timeline
    await timeline.append_event(
        db, session_id=session_id, game_id=game_id,
        event_type="event_check", actor_id=user_id,
        data={
            "event_name": event_name,
            "color": check_color,
            "ghost_id": ghost.id,
        },
        result_data={
            "player_total": player_total,
            "target_total": target_total,
            "success": check_success,
            "player_rolls": player_roll.individual_rolls,
            "flat_mod": flat_mod,
        },
    )

    await db.flush()

    return EngineResult(
        success=True,
        event_type="event_check",
        data={
            "event_name": event_name,
            "color": check_color,
            "effective_value": effective_value,
            "player_rolls": player_roll.individual_rolls,
            "flat_modifier": flat_mod,
            "player_total": player_total,
            "target_total": target_total,
            "check_success": check_success,
            "expired_buffs": expired,
        },
    )


async def handle_reroll(
    db: AsyncSession,
    game_id: str,
    session_id: str,
    user_id: str,
    ghost: Ghost,
    patient: Patient,
    event_name: str,
    ability_id: str,
    hard: bool = False,
) -> EngineResult:
    """Reroll an event check using a PrintAbility.

    Same-color reroll (hard=False): ability.color must match the check color.
    Hard reroll (hard=True): any color allowed, costs 1 MP.
    """
    event_type = "hard_reroll" if hard else "reroll"

    event_def = await get_active_event(db, session_id, event_name)
    if event_def is None:
        return EngineResult(
            success=False, event_type=event_type,
            error=f"No active event '{event_name}' in this session",
        )

    if event_def.target_roll_total is None:
        return EngineResult(
            success=False, event_type=event_type,
            error="No initial check has been made for this event yet",
        )

    # Get ability
    ability = await character.get_print_ability(db, ability_id)
    if ability is None:
        return EngineResult(
            success=False, event_type=event_type, error="Ability not found",
        )
    if ability.ghost_id != ghost.id:
        return EngineResult(
            success=False, event_type=event_type,
            error="Ability does not belong to this ghost",
        )

    # Check ability not already used in this event
    usage_result = await db.execute(
        select(EventAbilityUsage).where(
            EventAbilityUsage.event_def_id == event_def.id,
            EventAbilityUsage.ghost_id == ghost.id,
            EventAbilityUsage.ability_id == ability_id,
        )
    )
    if usage_result.scalar_one_or_none() is not None:
        return EngineResult(
            success=False, event_type=event_type,
            error="This ability has already been used for this event",
        )

    # Determine check color
    check_color = _resolve_color(event_def, None, patient)

    # Validate color match for same-color reroll
    if not hard and ability.color.upper() != check_color:
        return EngineResult(
            success=False, event_type=event_type,
            error=f"Ability color ({ability.color}) does not match check color ({check_color}). Use hard reroll instead.",
        )

    # Hard reroll costs 1 MP
    state_changes: list[StateChange] = []
    if hard:
        if ghost.mp < 1:
            return EngineResult(
                success=False, event_type=event_type,
                error="Not enough MP for hard reroll (requires 1 MP)",
            )
        old_mp = ghost.mp
        ghost.mp -= 1
        state_changes.append(StateChange(
            entity_type="ghost", entity_id=ghost.id,
            field="mp", old_value=str(old_mp), new_value=str(ghost.mp),
        ))

    # Consume ability use
    consumed = await character.use_print_ability(db, ability)
    if not consumed:
        return EngineResult(
            success=False, event_type=event_type,
            error="Ability has no uses remaining",
        )
    state_changes.append(StateChange(
        entity_type="print_ability", entity_id=ability_id,
        field="ability_count",
        old_value=str(ability.ability_count + 1),
        new_value=str(ability.ability_count),
    ))

    # Mark ability as used for this event
    usage = EventAbilityUsage(
        event_def_id=event_def.id,
        ghost_id=ghost.id,
        ability_id=ability_id,
    )
    db.add(usage)

    # Re-roll player dice
    cmyk = character.get_cmyk(ghost)
    buffs = await buff_mod.get_buffs(db, ghost.id)
    cmyk_adj, flat_mod = buff_mod.compute_buff_modifier(
        buffs, cmyk, settings.default_dice_type
    )

    effective_value = cmyk.get(check_color, 0) + cmyk_adj.get(check_color, 0)
    effective_value = max(0, effective_value)

    player_roll = roll_expression(
        f"{effective_value}d{settings.default_dice_type}"
    )
    player_total = player_roll.total + flat_mod
    target_total = event_def.target_roll_total
    check_success = player_total >= target_total

    # Tick buffs
    expired = await buff_mod.tick_buffs(db, ghost.id)

    # Record timeline
    await timeline.append_event(
        db, session_id=session_id, game_id=game_id,
        event_type=event_type, actor_id=user_id,
        data={
            "event_name": event_name,
            "ability_id": ability_id,
            "color": check_color,
            "ghost_id": ghost.id,
            "hard": hard,
        },
        result_data={
            "player_total": player_total,
            "target_total": target_total,
            "success": check_success,
            "player_rolls": player_roll.individual_rolls,
            "flat_mod": flat_mod,
        },
    )

    await db.flush()

    return EngineResult(
        success=True,
        event_type=event_type,
        data={
            "event_name": event_name,
            "ability_id": ability_id,
            "color": check_color,
            "effective_value": effective_value,
            "player_rolls": player_roll.individual_rolls,
            "flat_modifier": flat_mod,
            "player_total": player_total,
            "target_total": target_total,
            "check_success": check_success,
            "hard_reroll": hard,
            "expired_buffs": expired,
        },
        state_changes=state_changes,
    )


def _resolve_color(
    event_def: EventDefinition,
    player_choice: str | None,
    patient: Patient,
) -> str:
    """Determine check color: event restriction > player choice > soul_color."""
    if event_def.color_restriction:
        return event_def.color_restriction.upper()
    if player_choice:
        return player_choice.upper()
    return patient.soul_color.upper()
