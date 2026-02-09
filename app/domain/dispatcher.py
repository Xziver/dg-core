"""Event dispatcher — the single entry point for all game events."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, session as session_mod, timeline, world
from app.domain.rules import combat, narration, skill
from app.models.event import (
    ApplyFragmentPayload,
    AttackPayload,
    DefendPayload,
    EventType,
    GameEvent,
    HPChangePayload,
    PlayerJoinPayload,
    SectorTransitionPayload,
    SessionEndPayload,
    SessionStartPayload,
    SkillCheckPayload,
    UsePrintAbilityPayload,
)
from app.models.result import EngineResult, StateChange


async def dispatch(db: AsyncSession, event: GameEvent) -> EngineResult:
    """Route a GameEvent to its handler and return an EngineResult."""
    payload = event.payload
    et = payload.event_type

    try:
        if et == EventType.SESSION_START:
            return await _handle_session_start(db, event)
        elif et == EventType.SESSION_END:
            return await _handle_session_end(db, event)
        elif et == EventType.PLAYER_JOIN:
            return await _handle_player_join(db, event)
        elif et == EventType.PLAYER_LEAVE:
            return await _handle_player_leave(db, event)
        elif et == EventType.SKILL_CHECK:
            return await _handle_skill_check(db, event)
        elif et == EventType.ATTACK:
            return await _handle_attack(db, event)
        elif et == EventType.DEFEND:
            return await _handle_defend(db, event)
        elif et == EventType.USE_PRINT_ABILITY:
            return await _handle_use_print_ability(db, event)
        elif et == EventType.APPLY_FRAGMENT:
            return await _handle_apply_fragment(db, event)
        elif et == EventType.HP_CHANGE:
            return await _handle_hp_change(db, event)
        elif et == EventType.SECTOR_TRANSITION:
            return await _handle_sector_transition(db, event)
        else:
            return EngineResult(
                success=False, event_type=et, error=f"Unhandled event type: {et}"
            )
    except Exception as exc:
        return EngineResult(success=False, event_type=et, error=str(exc))


# --- System events ---

async def _handle_session_start(db: AsyncSession, event: GameEvent) -> EngineResult:
    s = await session_mod.start_session(db, event.session_id)
    await timeline.append_event(
        db, event.session_id, "session_start", actor_id=event.player_id
    )
    return EngineResult(
        success=True,
        event_type="session_start",
        data={"session_id": s.id, "status": s.status},
    )


async def _handle_session_end(db: AsyncSession, event: GameEvent) -> EngineResult:
    s = await session_mod.end_session(db, event.session_id)
    await timeline.append_event(
        db, event.session_id, "session_end", actor_id=event.player_id
    )
    return EngineResult(
        success=True,
        event_type="session_end",
        data={"session_id": s.id, "status": s.status},
    )


async def _handle_player_join(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: PlayerJoinPayload = event.payload  # type: ignore[assignment]
    link = await session_mod.join_session(
        db, event.session_id, event.player_id, role=payload.role
    )
    await timeline.append_event(
        db, event.session_id, "player_join",
        actor_id=event.player_id,
        data={"role": link.role},
    )
    return EngineResult(
        success=True,
        event_type="player_join",
        data={"player_id": event.player_id, "role": link.role},
    )


async def _handle_player_leave(db: AsyncSession, event: GameEvent) -> EngineResult:
    await timeline.append_event(
        db, event.session_id, "player_leave", actor_id=event.player_id
    )
    return EngineResult(
        success=True,
        event_type="player_leave",
        data={"player_id": event.player_id},
    )


# --- Action events ---

async def _handle_skill_check(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: SkillCheckPayload = event.payload  # type: ignore[assignment]

    # Find the player's ghost in this session
    ghost = await _find_player_ghost(db, event.session_id, event.player_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="skill_check", error="Player has no ghost in this session"
        )

    result = await skill.handle_skill_check(
        db,
        session_id=event.session_id,
        player_id=event.player_id,
        ghost_id=ghost.id,
        color=payload.color,
        difficulty=payload.difficulty,
        context=payload.context,
    )

    # Optional narration
    result = await narration.enrich_result_with_narration(
        db, event.session_id, result,
        character_name=ghost.name,
        context=payload.context,
    )
    return result


# --- Combat events ---

async def _handle_attack(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: AttackPayload = event.payload  # type: ignore[assignment]

    attacker = await character.get_ghost(db, payload.attacker_ghost_id)
    target = await character.get_ghost(db, payload.target_ghost_id)

    result = await combat.handle_attack(
        db,
        session_id=event.session_id,
        player_id=event.player_id,
        attacker_ghost_id=payload.attacker_ghost_id,
        target_ghost_id=payload.target_ghost_id,
        color_used=payload.color_used,
    )

    if attacker and target:
        result = await narration.enrich_result_with_narration(
            db, event.session_id, result,
            attacker_name=attacker.name,
            target_name=target.name,
        )
    return result


async def _handle_defend(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: DefendPayload = event.payload  # type: ignore[assignment]
    return await combat.handle_defend(
        db,
        session_id=event.session_id,
        player_id=event.player_id,
        defender_ghost_id=payload.defender_ghost_id,
        color_used=payload.color_used,
    )


async def _handle_use_print_ability(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: UsePrintAbilityPayload = event.payload  # type: ignore[assignment]
    # For MVP: use_print_ability without a prior roll context just records it
    ability = await character.get_print_ability(db, payload.ability_id)
    if ability is None:
        return EngineResult(
            success=False, event_type="use_print_ability", error="Ability not found"
        )
    consumed = await character.use_print_ability(db, ability)
    if not consumed:
        return EngineResult(
            success=False, event_type="use_print_ability", error="No uses remaining"
        )
    await timeline.append_event(
        db, event.session_id, "use_print_ability",
        actor_id=event.player_id,
        data={"ghost_id": payload.ghost_id, "ability_id": payload.ability_id},
    )
    return EngineResult(
        success=True,
        event_type="use_print_ability",
        data={"ability_id": payload.ability_id, "uses_remaining": ability.ability_count},
        state_changes=[
            StateChange(
                entity_type="print_ability",
                entity_id=payload.ability_id,
                field="ability_count",
                new_value=str(ability.ability_count),
            )
        ],
    )


# --- State events ---

async def _handle_apply_fragment(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: ApplyFragmentPayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="apply_fragment", error="Ghost not found"
        )
    new_cmyk = await character.apply_color_fragment(db, ghost, payload.color, payload.value)
    await timeline.append_event(
        db, event.session_id, "apply_fragment",
        actor_id=event.player_id,
        data={"ghost_id": payload.ghost_id, "color": payload.color, "value": payload.value},
    )
    return EngineResult(
        success=True,
        event_type="apply_fragment",
        data={"ghost_id": payload.ghost_id, "cmyk": new_cmyk},
        state_changes=[
            StateChange(
                entity_type="ghost",
                entity_id=payload.ghost_id,
                field=f"cmyk.{payload.color.upper()}",
                new_value=str(new_cmyk[payload.color.upper()]),
            )
        ],
    )


async def _handle_hp_change(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: HPChangePayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="hp_change", error="Ghost not found"
        )
    old_hp = ghost.hp
    new_hp, collapsed = await character.change_hp(db, ghost, payload.delta)
    await timeline.append_event(
        db, event.session_id, "hp_change",
        actor_id=event.player_id,
        data={"ghost_id": payload.ghost_id, "delta": payload.delta, "reason": payload.reason},
        result_data={"new_hp": new_hp, "collapsed": collapsed},
    )
    return EngineResult(
        success=True,
        event_type="hp_change",
        data={
            "ghost_id": payload.ghost_id,
            "old_hp": old_hp,
            "new_hp": new_hp,
            "collapsed": collapsed,
        },
        state_changes=[
            StateChange(
                entity_type="ghost",
                entity_id=payload.ghost_id,
                field="hp",
                old_value=str(old_hp),
                new_value=str(new_hp),
            )
        ],
    )


async def _handle_sector_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: SectorTransitionPayload = event.payload  # type: ignore[assignment]
    ws = await world.get_world_state(db, event.session_id)
    old_sector = ws.current_sector if ws else None
    await world.set_current_sector(db, event.session_id, payload.target_sector)
    await timeline.append_event(
        db, event.session_id, "sector_transition",
        actor_id=event.player_id,
        data={"from": old_sector, "to": payload.target_sector},
    )
    return EngineResult(
        success=True,
        event_type="sector_transition",
        data={"old_sector": old_sector, "new_sector": payload.target_sector},
        state_changes=[
            StateChange(
                entity_type="world_state",
                entity_id=event.session_id,
                field="current_sector",
                old_value=old_sector,
                new_value=payload.target_sector,
            )
        ],
    )


# --- Helpers ---

async def _find_player_ghost(
    db: AsyncSession, session_id: str, player_id: str
) -> character.Ghost | None:
    """Find the ghost belonging to this player's patient in this session."""
    from sqlalchemy import select
    from app.models.db_models import Patient, Ghost

    result = await db.execute(
        select(Ghost)
        .join(Patient, Ghost.patient_id == Patient.id)
        .where(Patient.player_id == player_id, Patient.session_id == session_id)
    )
    return result.scalar_one_or_none()
