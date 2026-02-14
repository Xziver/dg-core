"""Event dispatcher — the single entry point for all game events."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, game as game_mod, region as region_mod
from app.domain import communication, inventory
from app.domain import session as session_mod, timeline
from app.domain.rules import combat, event_check, narration
from app.models.db_models import GamePlayer, Ghost, Patient, Session
from app.models.event import (
    ApplyFragmentPayload,
    AttackPayload,
    CommAcceptPayload,
    CommCancelPayload,
    CommRejectPayload,
    CommRequestPayload,
    DefendPayload,
    EventCheckPayload,
    EventType,
    GameEvent,
    HPChangePayload,
    HardRerollPayload,
    ItemUsePayload,
    LocationTransitionPayload,
    PlayerJoinPayload,
    RegionTransitionPayload,
    RerollPayload,
    SessionStartPayload,
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
        # Event check system
        elif et == EventType.EVENT_CHECK:
            return await _handle_event_check(db, event)
        elif et == EventType.REROLL:
            return await _handle_reroll(db, event, hard=False)
        elif et == EventType.HARD_REROLL:
            return await _handle_reroll(db, event, hard=True)
        # Combat
        elif et == EventType.ATTACK:
            return await _handle_attack(db, event)
        elif et == EventType.DEFEND:
            return await _handle_defend(db, event)
        # Communication
        elif et == EventType.COMM_REQUEST:
            return await _handle_comm_request(db, event)
        elif et == EventType.COMM_ACCEPT:
            return await _handle_comm_accept(db, event)
        elif et == EventType.COMM_REJECT:
            return await _handle_comm_reject(db, event)
        elif et == EventType.COMM_CANCEL:
            return await _handle_comm_cancel(db, event)
        # Items
        elif et == EventType.ITEM_USE:
            return await _handle_item_use(db, event)
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
        db,
        game_id=event.game_id,
        started_by=event.user_id,
        region_id=payload.region_id,
        location_id=payload.location_id,
    )
    await timeline.append_event(
        db, session_id=s.id, game_id=event.game_id,
        event_type="session_start", actor_id=event.user_id,
    )
    return EngineResult(
        success=True,
        event_type="session_start",
        data={
            "session_id": s.id,
            "game_id": event.game_id,
            "status": s.status,
            "location_id": s.location_id,
        },
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


# --- Event check events ---

async def _handle_event_check(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: EventCheckPayload = event.payload  # type: ignore[assignment]

    patient = await _resolve_patient_for_event(db, event)
    if patient is None:
        return EngineResult(
            success=False, event_type="event_check",
            error="No character in this session's region",
        )

    ghost = await _find_player_ghost(db, patient_id=patient.id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="event_check",
            error="Player has no ghost in this game",
        )

    return await event_check.handle_event_check(
        db,
        game_id=event.game_id,
        session_id=sid,
        user_id=event.user_id,
        ghost=ghost,
        patient=patient,
        event_name=payload.event_name,
        color=payload.color,
    )


async def _handle_reroll(
    db: AsyncSession, event: GameEvent, hard: bool = False
) -> EngineResult:
    sid = _require_session(event)
    payload: RerollPayload | HardRerollPayload = event.payload  # type: ignore[assignment]

    patient = await _resolve_patient_for_event(db, event)
    event_type = "hard_reroll" if hard else "reroll"
    if patient is None:
        return EngineResult(
            success=False, event_type=event_type,
            error="No character in this session's region",
        )

    ghost = await _find_player_ghost(db, patient_id=patient.id)
    if ghost is None:
        return EngineResult(
            success=False, event_type=event_type,
            error="Player has no ghost in this game",
        )

    return await event_check.handle_reroll(
        db,
        game_id=event.game_id,
        session_id=sid,
        user_id=event.user_id,
        ghost=ghost,
        patient=patient,
        event_name=payload.event_name,
        ability_id=payload.ability_id,
        hard=hard,
    )


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


# --- Communication events ---

async def _handle_comm_request(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: CommRequestPayload = event.payload  # type: ignore[assignment]

    patient = await _resolve_patient_for_event(db, event)
    if patient is None:
        return EngineResult(
            success=False, event_type="comm_request",
            error="No active character found",
        )

    comm = await communication.request_communication(
        db,
        game_id=event.game_id,
        initiator_patient_id=patient.id,
        target_patient_id=payload.target_patient_id,
    )

    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="comm_request", actor_id=event.user_id,
        data={
            "request_id": comm.id,
            "target_patient_id": payload.target_patient_id,
        },
    )

    return EngineResult(
        success=True,
        event_type="comm_request",
        data={
            "request_id": comm.id,
            "initiator_patient_id": patient.id,
            "target_patient_id": payload.target_patient_id,
            "status": comm.status,
        },
    )


async def _handle_comm_accept(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: CommAcceptPayload = event.payload  # type: ignore[assignment]

    result_data = await communication.accept_communication(
        db, request_id=payload.request_id, ability_id=payload.ability_id
    )

    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="comm_accept", actor_id=event.user_id,
        data={"request_id": payload.request_id},
    )

    return EngineResult(
        success=True,
        event_type="comm_accept",
        data=result_data,
    )


async def _handle_comm_reject(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: CommRejectPayload = event.payload  # type: ignore[assignment]

    comm = await communication.reject_communication(db, payload.request_id)

    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="comm_reject", actor_id=event.user_id,
        data={"request_id": payload.request_id},
    )

    return EngineResult(
        success=True,
        event_type="comm_reject",
        data={"request_id": comm.id, "status": comm.status},
    )


async def _handle_comm_cancel(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: CommCancelPayload = event.payload  # type: ignore[assignment]

    comm = await communication.cancel_communication(db, payload.request_id)

    await timeline.append_event(
        db, session_id=sid, game_id=event.game_id,
        event_type="comm_cancel", actor_id=event.user_id,
        data={"request_id": payload.request_id},
    )

    return EngineResult(
        success=True,
        event_type="comm_cancel",
        data={"request_id": comm.id, "status": comm.status},
    )


# --- Item events ---

async def _handle_item_use(db: AsyncSession, event: GameEvent) -> EngineResult:
    sid = _require_session(event)
    payload: ItemUsePayload = event.payload  # type: ignore[assignment]

    patient = await _resolve_patient_for_event(db, event)
    if patient is None:
        return EngineResult(
            success=False, event_type="item_use",
            error="No active character found",
        )

    ghost = await _find_player_ghost(db, patient_id=patient.id)
    if ghost is None:
        return EngineResult(
            success=False, event_type="item_use",
            error="Player has no ghost in this game",
        )

    result = await inventory.use_item(
        db,
        game_id=event.game_id,
        patient_id=patient.id,
        item_def_id=payload.item_def_id,
        ghost=ghost,
    )

    if result.success:
        await timeline.append_event(
            db, session_id=sid, game_id=event.game_id,
            event_type="item_use", actor_id=event.user_id,
            data={"item_def_id": payload.item_def_id},
            result_data=result.data,
        )

    return result


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
    patient = await region_mod.move_character(
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
                entity_type="patient",
                entity_id=patient.id,
                field="current_region_id",
                new_value=payload.target_region_id,
            )
        ],
    )


async def _handle_location_transition(db: AsyncSession, event: GameEvent) -> EngineResult:
    payload: LocationTransitionPayload = event.payload  # type: ignore[assignment]
    patient = await region_mod.move_character(
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
                entity_type="patient",
                entity_id=patient.id,
                field="current_location_id",
                new_value=payload.target_location_id,
            )
        ],
    )


# --- Helpers ---

async def _resolve_patient_for_event(
    db: AsyncSession, event: GameEvent
) -> Patient | None:
    """Hybrid character resolution: session region → patient, or fallback to active_patient_id."""
    if event.session_id:
        # Resolve by session region
        session_result = await db.execute(
            select(Session).where(Session.id == event.session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is not None and session.region_id is not None:
            patient_result = await db.execute(
                select(Patient).where(
                    Patient.user_id == event.user_id,
                    Patient.game_id == event.game_id,
                    Patient.current_region_id == session.region_id,
                )
            )
            return patient_result.scalar_one_or_none()

    # Fallback: use active_patient_id from GamePlayer
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == event.game_id,
            GamePlayer.user_id == event.user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        return None

    patient_result = await db.execute(
        select(Patient).where(Patient.id == gp.active_patient_id)
    )
    return patient_result.scalar_one_or_none()


async def _find_player_ghost(
    db: AsyncSession,
    game_id: str | None = None,
    user_id: str | None = None,
    patient_id: str | None = None,
) -> Ghost | None:
    """Find the ghost for a patient. Accepts direct patient_id or resolves via GamePlayer."""
    if patient_id is None:
        if game_id is None or user_id is None:
            return None
        gp_result = await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id,
                GamePlayer.user_id == user_id,
            )
        )
        gp = gp_result.scalar_one_or_none()
        if gp is None or gp.active_patient_id is None:
            return None
        patient_id = gp.active_patient_id

    result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient_id)
    )
    return result.scalar_one_or_none()
