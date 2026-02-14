"""Event dispatcher — the single entry point for all game events."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, game as game_mod, region as region_mod
from app.domain import session as session_mod, timeline
from app.domain.rules import combat, narration, skill
from app.models.event import (
    ApplyFragmentPayload,
    AttackPayload,
    DefendPayload,
    EventType,
    GameEvent,
    HPChangePayload,
    LocationTransitionPayload,
    PlayerJoinPayload,
    RegionTransitionPayload,
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
        # Game lifecycle
        if et == EventType.GAME_START:
            return await _handle_game_start(db, event)
        elif et == EventType.GAME_END:
            return await _handle_game_end(db, event)
        elif et == EventType.PLAYER_JOIN:
            return await _handle_player_join(db, event)
        elif et == EventType.PLAYER_LEAVE:
            return await _handle_player_leave(db, event)
        # Session lifecycle
        elif et == EventType.SESSION_START:
            return await _handle_session_start(db, event)
        elif et == EventType.SESSION_END:
            return await _handle_session_end(db, event)
        # Actions
        elif et == EventType.SKILL_CHECK:
            return await _handle_skill_check(db, event)
        elif et == EventType.ATTACK:
            return await _handle_attack(db, event)
        elif et == EventType.DEFEND:
            return await _handle_defend(db, event)
        elif et == EventType.USE_PRINT_ABILITY:
            return await _handle_use_print_ability(db, event)
        # State changes
        elif et == EventType.APPLY_FRAGMENT:
            return await _handle_apply_fragment(db, event)
        elif et == EventType.HP_CHANGE:
            return await _handle_hp_change(db, event)
        elif et == EventType.REGION_TRANSITION:
            return await _handle_region_transition(db, event)
        elif et == EventType.LOCATION_TRANSITION:
            return await _handle_location_transition(db, event)
        else:
            return EngineResult(
                success=False, event_type=et, error=f"Unhandled event type: {et}"
            )
    except Exception as exc:
        return EngineResult(success=False, event_type=et, error=str(exc))


def _require_session(event: GameEvent) -> str:
    """Return session_id or raise if missing."""
    if not event.session_id:
        raise ValueError("session_id is required for this event type")
    return event.session_id


# --- Game lifecycle events ---

async def _handle_game_start(db: AsyncSession, event: GameEvent) -> EngineResult:
    game = await game_mod.start_game(db, event.game_id)
    return EngineResult(
        success=True,
        event_type="game_start",
        data={"game_id": game.id, "status": game.status},
    )


async def _handle_game_end(db: AsyncSession, event: GameEvent) -> EngineResult:
    game = await game_mod.end_game(db, event.game_id)
    return EngineResult(
        success=True,
        event_type="game_end",
        data={"game_id": game.id, "status": game.status},
    )


async def _handle_player_join(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: PlayerJoinPayload = event.payload  # type: ignore[assignment]
    link = await game_mod.join_game(
        db, event.game_id, event.user_id, role=payload.role
    )
    return EngineResult(
        success=True,
        event_type="player_join",
        data={"game_id": event.game_id, "user_id": event.user_id, "role": link.role},
    )


async def _handle_player_leave(db: AsyncSession, event: GameEvent) -> EngineResult:
    return EngineResult(
        success=True,
        event_type="player_leave",
        data={"user_id": event.user_id},
    )


# --- Session lifecycle events ---

async def _handle_session_start(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: SessionStartPayload = event.payload  # type: ignore[assignment]
    s = await session_mod.start_session(
        db, game_id=event.game_id, started_by=event.user_id, region_id=payload.region_id
    )
    await timeline.append_event(
        db, session_id=s.id, game_id=event.game_id,
        event_type="session_start", actor_id=event.user_id,
    )
    return EngineResult(
        success=True,
        event_type="session_start",
        data={"session_id": s.id, "game_id": event.game_id, "status": s.status},
    )


async def _handle_session_end(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    s = await session_mod.end_session(db, sid)
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="session_end", actor_id=event.user_id,
    )
    return EngineResult(
        success=True,
        event_type="session_end",
        data={"session_id": s.id, "status": s.status},
    )


# --- Action events ---

async def _handle_skill_check(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: SkillCheckPayload = event.payload  # type: ignore[assignment]

    ghost = await _find_player_ghost(db, event.game_id, event.user_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="skill_check", error="Player has no ghost in this game"
        )

    result = await skill.handle_skill_check(
        db,
        game_id=event.game_id,
        session_id=sid,
        user_id=event.user_id,
        ghost_id=ghost.id,
        color=payload.color,
        difficulty=payload.difficulty,
        context=payload.context,
    )

    result = await narration.enrich_result_with_narration(
        db, event.game_id, result,
        character_name=ghost.name,
        context=payload.context,
    )
    return result


# --- Combat events ---

async def _handle_attack(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: AttackPayload = event.payload  # type: ignore[assignment]

    attacker = await character.get_ghost(db, payload.attacker_ghost_id)
    target = await character.get_ghost(db, payload.target_ghost_id)

    result = await combat.handle_attack(
        db,
        game_id=event.game_id,
        session_id=sid,
        user_id=event.user_id,
        attacker_ghost_id=payload.attacker_ghost_id,
        target_ghost_id=payload.target_ghost_id,
        color_used=payload.color_used,
    )

    if attacker and target:
        result = await narration.enrich_result_with_narration(
            db, event.game_id, result,
            attacker_name=attacker.name,
            target_name=target.name,
        )
    return result


async def _handle_defend(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: DefendPayload = event.payload  # type: ignore[assignment]
    return await combat.handle_defend(
        db,
        game_id=event.game_id,
        session_id=sid,
        user_id=event.user_id,
        defender_ghost_id=payload.defender_ghost_id,
        color_used=payload.color_used,
    )


async def _handle_use_print_ability(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: UsePrintAbilityPayload = event.payload  # type: ignore[assignment]
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
        db, session_id=sid, game_id=event.game_id,
        event_type="use_print_ability",
        actor_id=event.user_id,
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
    sid = _require_session(event)
    payload: ApplyFragmentPayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="apply_fragment", error="Ghost not found"
        )
    fragment_result = await character.apply_color_fragment(db, ghost, payload.color, payload.value)
    new_cmyk = fragment_result["cmyk"]
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="apply_fragment",
        actor_id=event.user_id,
        data={"ghost_id": payload.ghost_id, "color": payload.color, "value": payload.value},
    )
    return EngineResult(
        success=True,
        event_type="apply_fragment",
        data={"ghost_id": payload.ghost_id, "cmyk": new_cmyk, "fragment_id": fragment_result["fragment_id"]},
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
    sid = _require_session(event)
    payload: HPChangePayload = event.payload  # type: ignore[assignment]
    ghost = await character.get_ghost(db, payload.ghost_id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="hp_change", error="Ghost not found"
        )
    old_hp = ghost.hp
    new_hp, collapsed = await character.change_hp(db, ghost, payload.delta)
    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="hp_change",
        actor_id=event.user_id,
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


async def _handle_region_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: RegionTransitionPayload = event.payload  # type: ignore[assignment]
    await region_mod.move_player(
        db, event.game_id, event.user_id, region_id=payload.target_region_id
    )
    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="region_transition", actor_id=event.user_id,
            data={"target_region_id": payload.target_region_id},
        )
    return EngineResult(
        success=True,
        event_type="region_transition",
        data={"user_id": event.user_id, "region_id": payload.target_region_id},
        state_changes=[
            StateChange(
                entity_type="game_player",
                entity_id=event.user_id,
                field="current_region_id",
                new_value=payload.target_region_id,
            )
        ],
    )


async def _handle_location_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: LocationTransitionPayload = event.payload  # type: ignore[assignment]
    await region_mod.move_player(
        db, event.game_id, event.user_id, location_id=payload.target_location_id
    )
    if event.session_id:
        await timeline.append_event(
            db, session_id=event.session_id, game_id=event.game_id,
            event_type="location_transition", actor_id=event.user_id,
            data={"target_location_id": payload.target_location_id},
        )
    return EngineResult(
        success=True,
        event_type="location_transition",
        data={"user_id": event.user_id, "location_id": payload.target_location_id},
        state_changes=[
            StateChange(
                entity_type="game_player",
                entity_id=event.user_id,
                field="current_location_id",
                new_value=payload.target_location_id,
            )
        ],
    )


# --- Helpers ---

async def _find_player_ghost(
    db: AsyncSession, game_id: str, user_id: str
) -> character.Ghost | None:
    """Find the ghost for this user's active patient in this game."""
    from sqlalchemy import select
    from app.models.db_models import GamePlayer, Ghost

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        return None

    result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == gp.active_patient_id)
    )
    return result.scalar_one_or_none()
