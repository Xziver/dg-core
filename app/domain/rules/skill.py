"""Skill check rule — CMYK dice roll + difficulty comparison."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, timeline
from app.infra.config import settings
from app.models.result import DiceRollResult, EngineResult, StateChange
from app.modules.dice import roller


async def handle_skill_check(
    db: AsyncSession,
    session_id: str,
    player_id: str,
    ghost_id: str,
    color: str,
    difficulty: int,
    context: str = "",
) -> EngineResult:
    """Perform a skill check: pick color → get dice count → roll → compare difficulty."""
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        return EngineResult(success=False, event_type="skill_check", error="Ghost not found")

    color_value = character.get_color_value(ghost, color)
    dice_type = settings.default_dice_type
    dice_roll = roller.roll(color_value, dice_type, difficulty)

    roll_result = DiceRollResult(
        dice_count=dice_roll.dice_count,
        dice_type=dice_roll.dice_type,
        results=dice_roll.results,
        total=dice_roll.total,
        difficulty=dice_roll.difficulty,
        success=dice_roll.success,
    )

    await timeline.append_event(
        db,
        session_id=session_id,
        event_type="skill_check",
        actor_id=player_id,
        data={
            "ghost_id": ghost_id,
            "color": color,
            "difficulty": difficulty,
            "context": context,
        },
        result_data={
            "total": dice_roll.total,
            "success": dice_roll.success,
            "results": dice_roll.results,
        },
    )

    return EngineResult(
        success=True,
        event_type="skill_check",
        data={
            "ghost_id": ghost_id,
            "color": color,
            "roll_total": dice_roll.total,
            "difficulty": difficulty,
            "check_success": dice_roll.success,
            "dice_results": dice_roll.results,
        },
        rolls=[roll_result],
    )


async def handle_reroll(
    db: AsyncSession,
    session_id: str,
    player_id: str,
    ghost_id: str,
    ability_id: str,
    original_roll: DiceRollResult,
) -> EngineResult:
    """Use a print ability to reroll a previous skill check."""
    ability = await character.get_print_ability(db, ability_id)
    if ability is None:
        return EngineResult(success=False, event_type="use_print_ability", error="Ability not found")

    consumed = await character.use_print_ability(db, ability)
    if not consumed:
        return EngineResult(
            success=False, event_type="use_print_ability", error="Ability has no uses left"
        )

    original_dice = roller.DiceRoll(
        dice_count=original_roll.dice_count,
        dice_type=original_roll.dice_type,
        results=original_roll.results,
        total=original_roll.total,
        difficulty=original_roll.difficulty,
        success=original_roll.success,
    )
    new_roll = roller.reroll(original_dice)

    roll_result = DiceRollResult(
        dice_count=new_roll.dice_count,
        dice_type=new_roll.dice_type,
        results=new_roll.results,
        total=new_roll.total,
        difficulty=new_roll.difficulty,
        success=new_roll.success,
        rerolled=True,
        reroll_results=new_roll.reroll_results,
    )

    state_changes = [
        StateChange(
            entity_type="print_ability",
            entity_id=ability_id,
            field="ability_count",
            old_value=str(ability.ability_count + 1),
            new_value=str(ability.ability_count),
        )
    ]

    await timeline.append_event(
        db,
        session_id=session_id,
        event_type="use_print_ability",
        actor_id=player_id,
        data={"ghost_id": ghost_id, "ability_id": ability_id},
        result_data={"total": new_roll.total, "success": new_roll.success, "rerolled": True},
    )

    return EngineResult(
        success=True,
        event_type="use_print_ability",
        data={
            "ghost_id": ghost_id,
            "ability_id": ability_id,
            "roll_total": new_roll.total,
            "check_success": new_roll.success,
            "reroll_results": new_roll.reroll_results,
        },
        rolls=[roll_result],
        state_changes=state_changes,
    )
