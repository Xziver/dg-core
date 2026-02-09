"""Combat rule — attack/defend flow with damage, fragments, HP, collapse detection."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, timeline
from app.infra.config import settings
from app.models.result import DiceRollResult, EngineResult, StateChange
from app.modules.dice import roller


async def handle_attack(
    db: AsyncSession,
    session_id: str,
    player_id: str,
    attacker_ghost_id: str,
    target_ghost_id: str,
    color_used: str,
) -> EngineResult:
    """Process an attack: attacker rolls vs defender's color value as difficulty."""
    attacker = await character.get_ghost(db, attacker_ghost_id)
    target = await character.get_ghost(db, target_ghost_id)

    if attacker is None:
        return EngineResult(success=False, event_type="attack", error="Attacker ghost not found")
    if target is None:
        return EngineResult(success=False, event_type="attack", error="Target ghost not found")

    # Attacker rolls using their color value
    atk_value = character.get_color_value(attacker, color_used)
    dice_type = settings.default_dice_type
    # Difficulty = target's value in the same color + base threshold
    def_value = character.get_color_value(target, color_used)
    difficulty = max(def_value * dice_type // 2 + 1, 2)

    atk_roll = roller.roll(atk_value, dice_type, difficulty)

    roll_result = DiceRollResult(
        dice_count=atk_roll.dice_count,
        dice_type=atk_roll.dice_type,
        results=atk_roll.results,
        total=atk_roll.total,
        difficulty=atk_roll.difficulty,
        success=atk_roll.success,
    )

    state_changes: list[StateChange] = []

    if atk_roll.success:
        # Damage: difference between roll and difficulty, min 1
        damage = max(atk_roll.total - difficulty, 1)
        new_hp, collapsed = await character.change_hp(db, target, -damage)

        state_changes.append(
            StateChange(
                entity_type="ghost",
                entity_id=target_ghost_id,
                field="hp",
                old_value=str(new_hp + damage),
                new_value=str(new_hp),
            )
        )

        # Drop a color fragment on successful hit
        cmyk = await character.apply_color_fragment(db, attacker, color_used, value=1)
        state_changes.append(
            StateChange(
                entity_type="ghost",
                entity_id=attacker_ghost_id,
                field=f"cmyk.{color_used.upper()}",
                old_value=str(cmyk[color_used.upper()] - 1),
                new_value=str(cmyk[color_used.upper()]),
            )
        )

        data = {
            "hit": True,
            "damage": damage,
            "target_hp": new_hp,
            "collapsed": collapsed,
            "fragment_gained": {"color": color_used.upper(), "value": 1},
        }
    else:
        damage = 0
        collapsed = False
        data = {"hit": False, "damage": 0}

    await timeline.append_event(
        db,
        session_id=session_id,
        event_type="attack",
        actor_id=player_id,
        data={
            "attacker_ghost_id": attacker_ghost_id,
            "target_ghost_id": target_ghost_id,
            "color_used": color_used,
        },
        result_data={
            "roll_total": atk_roll.total,
            "difficulty": difficulty,
            "success": atk_roll.success,
            "damage": damage,
            "collapsed": collapsed,
        },
    )

    return EngineResult(
        success=True,
        event_type="attack",
        data=data,
        rolls=[roll_result],
        state_changes=state_changes,
    )


async def handle_defend(
    db: AsyncSession,
    session_id: str,
    player_id: str,
    defender_ghost_id: str,
    color_used: str,
) -> EngineResult:
    """Defensive action: roll to reduce incoming damage or gain a buff."""
    ghost = await character.get_ghost(db, defender_ghost_id)
    if ghost is None:
        return EngineResult(success=False, event_type="defend", error="Ghost not found")

    color_value = character.get_color_value(ghost, color_used)
    dice_type = settings.default_dice_type
    difficulty = dice_type  # Base difficulty for defense

    defense_roll = roller.roll(color_value, dice_type, difficulty)

    roll_result = DiceRollResult(
        dice_count=defense_roll.dice_count,
        dice_type=defense_roll.dice_type,
        results=defense_roll.results,
        total=defense_roll.total,
        difficulty=defense_roll.difficulty,
        success=defense_roll.success,
    )

    data = {
        "defender_ghost_id": defender_ghost_id,
        "defense_success": defense_roll.success,
        "defense_value": defense_roll.total if defense_roll.success else 0,
    }

    await timeline.append_event(
        db,
        session_id=session_id,
        event_type="defend",
        actor_id=player_id,
        data={"defender_ghost_id": defender_ghost_id, "color_used": color_used},
        result_data={"total": defense_roll.total, "success": defense_roll.success},
    )

    return EngineResult(
        success=True,
        event_type="defend",
        data=data,
        rolls=[roll_result],
    )
