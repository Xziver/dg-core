"""Bot API — game event submission, state queries, and management endpoints."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    buff as buff_mod,
    character,
    communication,
    game as game_mod,
    inventory,
    permissions,
    session as session_mod,
    timeline,
)
from app.domain.dispatcher import dispatch
from app.domain.rules import event_check
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.infra.ws_manager import ws_manager
from app.models.db_models import GamePlayer, Ghost, Patient, User
from app.models.event import GameEvent
from app.modules.dice.parser import roll_expression

router = APIRouter(prefix="/api/bot", tags=["bot"])


# --- Request schemas ---


class SwitchCharacterRequest(BaseModel):
    patient_id: str
    user_id: str | None = None


class UnlockArchiveRequest(BaseModel):
    fragment_id: str
    user_id: str | None = None


class SetAttributeRequest(BaseModel):
    ghost_id: str
    attribute: str  # hp, mp, hp_max, mp_max, cmyk.C/M/Y/K
    value: int


class AddBuffRequest(BaseModel):
    ghost_id: str
    name: str
    expression: str
    remaining_rounds: int = 1


class DefineEventRequest(BaseModel):
    game_id: str
    name: str
    expression: str
    color_restriction: str | None = None


class RollRequest(BaseModel):
    expression: str
    game_id: str | None = None
    user_id: str | None = None


class CreateItemRequest(BaseModel):
    name: str
    description: str | None = None
    item_type: str = "generic"
    effect: dict | None = None
    stackable: bool = True


class GrantItemRequest(BaseModel):
    patient_id: str
    item_def_id: str
    count: int = 1


class AddSessionPlayerRequest(BaseModel):
    patient_id: str


# --- Event dispatch ---


@router.post("/events")
async def submit_event(
    event: GameEvent,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Submit a game event to the engine dispatcher.

    Bot proxy pattern: the authenticated caller (via X-API-Key) is the bot
    service. The ``user_id`` field in the GameEvent body identifies the
    player on whose behalf the event is submitted. The caller is trusted —
    no authorization check is performed between caller and event user_id.
    """
    result = await dispatch(db, event)
    await ws_manager.broadcast_to_game(event.game_id, result)
    return result.model_dump()


# --- Game queries ---


@router.get("/games/{game_id}")
async def get_game(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    game = await game_mod.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    players = await game_mod.get_game_players(db, game_id)
    return {
        "game_id": game.id,
        "name": game.name,
        "status": game.status,
        "config": json.loads(game.config_json) if game.config_json else None,
        "players": [
            {
                "user_id": p.user_id,
                "role": p.role,
                "active_patient_id": p.active_patient_id,
            }
            for p in players
        ],
    }


# --- Character management ---


@router.get("/games/{game_id}/characters/active")
async def get_active_character(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Get the active character (patient + ghost + abilities + buffs)."""
    acting_user_id = user_id or current_user.id

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None:
        raise HTTPException(status_code=404, detail="Player not in game")
    if gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character")

    patient = await character.get_patient(db, gp.active_patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == patient.id)
    )
    ghost = ghost_result.scalar_one_or_none()

    result: dict = {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "soul_color": patient.soul_color,
            "gender": patient.gender,
            "age": patient.age,
            "identity": patient.identity,
            "region_id": patient.current_region_id,
            "location_id": patient.current_location_id,
        },
    }

    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        buffs = await buff_mod.get_buffs(db, ghost.id)
        result["ghost"] = {
            "id": ghost.id,
            "name": ghost.name,
            "cmyk": json.loads(ghost.cmyk_json),
            "hp": ghost.hp,
            "hp_max": ghost.hp_max,
            "mp": ghost.mp,
            "mp_max": ghost.mp_max,
            "abilities": [
                {
                    "id": a.id,
                    "name": a.name,
                    "color": a.color,
                    "description": a.description,
                    "ability_count": a.ability_count,
                }
                for a in abilities
            ],
            "buffs": [
                {
                    "id": b.id,
                    "name": b.name,
                    "expression": b.expression,
                    "buff_type": b.buff_type,
                    "remaining_rounds": b.remaining_rounds,
                }
                for b in buffs
            ],
        }

    return result


@router.get("/games/{game_id}/characters")
async def list_characters(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """List all of a user's characters in a game."""
    acting_user_id = user_id or current_user.id
    patients = await character.get_patients_in_game(db, game_id, acting_user_id)
    return {
        "game_id": game_id,
        "characters": [
            {
                "id": p.id,
                "name": p.name,
                "soul_color": p.soul_color,
                "region_id": p.current_region_id,
                "location_id": p.current_location_id,
            }
            for p in patients
        ],
    }


@router.put("/games/{game_id}/active-character")
async def switch_active_character(
    game_id: str,
    body: SwitchCharacterRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Switch the player's active character in a game."""
    acting_user_id = body.user_id or current_user.id
    try:
        gp = await game_mod.switch_character(
            db, game_id, acting_user_id, body.patient_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "game_id": gp.game_id,
        "user_id": gp.user_id,
        "active_patient_id": gp.active_patient_id,
    }


@router.put("/games/{game_id}/characters/attributes")
async def set_character_attribute(
    game_id: str,
    body: SetAttributeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Set a ghost attribute. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    ghost = await character.get_ghost(db, body.ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")

    try:
        await character.set_ghost_attribute(db, ghost, body.attribute, body.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "ghost_id": ghost.id,
        "attribute": body.attribute,
        "value": body.value,
    }


@router.delete("/games/{game_id}/characters/{patient_id}")
async def delete_character(
    game_id: str,
    patient_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Delete a character. DM or character owner."""
    acting_user_id = user_id or current_user.id

    patient = await character.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Character not found")

    # Allow DM or owner
    is_owner = patient.user_id == acting_user_id
    is_dm = False
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
        is_dm = True
    except ValueError:
        pass

    if not is_owner and not is_dm:
        raise HTTPException(status_code=403, detail="Only DM or character owner can delete")

    try:
        await character.delete_patient(db, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"deleted": patient_id}


@router.post("/games/{game_id}/unlock-archive")
async def unlock_archive(
    game_id: str,
    body: UnlockArchiveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Redeem a color fragment to unlock the corresponding origin archive."""
    acting_user_id = body.user_id or current_user.id

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character in this game")

    ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == gp.active_patient_id)
    )
    ghost = ghost_result.scalar_one_or_none()
    if ghost is None:
        raise HTTPException(status_code=400, detail="No ghost assigned to active character")

    try:
        result = await character.unlock_archive(db, body.fragment_id, ghost.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# --- Dice rolling ---


@router.post("/roll")
async def roll_dice(
    body: RollRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Roll dice with a general expression. Optionally resolves CMYK from active character."""
    cmyk_values = None

    if body.game_id:
        acting_user_id = body.user_id or current_user.id
        gp_result = await db.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == body.game_id,
                GamePlayer.user_id == acting_user_id,
            )
        )
        gp = gp_result.scalar_one_or_none()
        if gp and gp.active_patient_id:
            ghost_result = await db.execute(
                select(Ghost).where(Ghost.current_patient_id == gp.active_patient_id)
            )
            ghost = ghost_result.scalar_one_or_none()
            if ghost:
                cmyk_values = character.get_cmyk(ghost)

    try:
        result = roll_expression(body.expression, cmyk_values)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "expression": result.expression,
        "individual_rolls": result.individual_rolls,
        "kept_rolls": result.kept_rolls,
        "subtotal": result.subtotal,
        "modifier": result.modifier,
        "total": result.total,
    }


# --- Buff management ---


@router.post("/games/{game_id}/buffs")
async def add_buff(
    game_id: str,
    body: AddBuffRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Add a buff to a ghost. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    ghost = await character.get_ghost(db, body.ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")

    buff = await buff_mod.add_buff(
        db,
        ghost_id=ghost.id,
        game_id=game_id,
        name=body.name,
        expression=body.expression,
        remaining_rounds=body.remaining_rounds,
        created_by=acting_user_id,
    )
    return {
        "id": buff.id,
        "name": buff.name,
        "expression": buff.expression,
        "buff_type": buff.buff_type,
        "remaining_rounds": buff.remaining_rounds,
    }


@router.get("/games/{game_id}/ghosts/{ghost_id}/buffs")
async def list_buffs(
    game_id: str,
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List buffs on a ghost."""
    buffs = await buff_mod.get_buffs(db, ghost_id)
    return {
        "ghost_id": ghost_id,
        "buffs": [
            {
                "id": b.id,
                "name": b.name,
                "expression": b.expression,
                "buff_type": b.buff_type,
                "remaining_rounds": b.remaining_rounds,
            }
            for b in buffs
        ],
    }


@router.delete("/games/{game_id}/buffs/{buff_id}")
async def remove_buff(
    game_id: str,
    buff_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Remove a buff. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        await buff_mod.remove_buff(db, buff_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"deleted": buff_id}


# --- Event definition management ---


@router.post("/sessions/{session_id}/events/define")
async def define_event(
    session_id: str,
    body: DefineEventRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Define an event check target for a session. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, body.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    event_def = await event_check.set_event(
        db,
        session_id=session_id,
        game_id=body.game_id,
        name=body.name,
        expression=body.expression,
        color_restriction=body.color_restriction,
        created_by=acting_user_id,
    )
    return {
        "id": event_def.id,
        "name": event_def.name,
        "expression": event_def.expression,
        "color_restriction": event_def.color_restriction,
        "is_active": event_def.is_active,
    }


@router.get("/sessions/{session_id}/events")
async def list_events(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List active events in a session."""
    events = await event_check.get_active_events(db, session_id)
    return {
        "session_id": session_id,
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "expression": e.expression,
                "color_restriction": e.color_restriction,
                "target_roll_total": e.target_roll_total,
            }
            for e in events
        ],
    }


@router.delete("/sessions/{session_id}/events/{event_id}")
async def deactivate_event(
    session_id: str,
    event_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Deactivate an event. DM only."""
    acting_user_id = user_id or current_user.id

    try:
        event_def = await event_check.deactivate_event_by_id(db, event_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        await permissions.require_dm(db, event_def.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {"deactivated": event_id}


# --- Session management ---


@router.post("/sessions/{session_id}/pause")
async def pause_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Pause an active session. DM only."""
    acting_user_id = user_id or current_user.id
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await permissions.require_dm(db, session.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        s = await session_mod.pause_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"session_id": s.id, "status": s.status}


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Resume a paused session. DM only."""
    acting_user_id = user_id or current_user.id
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await permissions.require_dm(db, session.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        s = await session_mod.resume_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"session_id": s.id, "status": s.status}


@router.post("/sessions/{session_id}/players")
async def add_session_player(
    session_id: str,
    body: AddSessionPlayerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Add a player to a session. DM only."""
    acting_user_id = user_id or current_user.id
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await permissions.require_dm(db, session.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        sp = await session_mod.add_player_to_session(db, session_id, body.patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"session_id": session_id, "patient_id": sp.patient_id}


@router.delete("/sessions/{session_id}/players/{patient_id}")
async def remove_session_player(
    session_id: str,
    patient_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Remove a player from a session. DM only."""
    acting_user_id = user_id or current_user.id
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await permissions.require_dm(db, session.game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        await session_mod.remove_player_from_session(db, session_id, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"removed": patient_id}


@router.get("/sessions/{session_id}/info")
async def get_session_info(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get session info including players and active events."""
    try:
        info = await session_mod.get_session_info(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return info


# --- Timeline ---


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> dict:
    session = await session_mod.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = await timeline.get_timeline(db, session_id, limit=limit, offset=offset)
    return {
        "session_id": session_id,
        "events": [
            {
                "id": e.id,
                "seq": e.seq,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": json.loads(e.data_json) if e.data_json else None,
                "result": json.loads(e.result_json) if e.result_json else None,
                "narrative": e.narrative,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


@router.get("/games/{game_id}/timeline")
async def get_game_timeline(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 100,
    offset: int = 0,
) -> dict:
    events = await timeline.get_game_timeline(db, game_id, limit=limit, offset=offset)
    return {
        "game_id": game_id,
        "events": [
            {
                "id": e.id,
                "seq": e.seq,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "data": json.loads(e.data_json) if e.data_json else None,
                "result": json.loads(e.result_json) if e.result_json else None,
                "narrative": e.narrative,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


# --- Communication ---


@router.get("/games/{game_id}/communications/pending")
async def list_pending_communications(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """List pending communication requests targeting the user's active character."""
    acting_user_id = user_id or current_user.id

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character in this game")

    pending = await communication.get_pending_requests(db, game_id, gp.active_patient_id)
    return {
        "game_id": game_id,
        "pending_requests": [
            {
                "id": r.id,
                "initiator_patient_id": r.initiator_patient_id,
                "target_patient_id": r.target_patient_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in pending
        ],
    }


# --- Print abilities ---


@router.get("/ghosts/{ghost_id}/abilities")
async def list_abilities(
    ghost_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List abilities on a ghost."""
    abilities = await character.get_print_abilities(db, ghost_id)
    return {
        "ghost_id": ghost_id,
        "abilities": [
            {
                "id": a.id,
                "name": a.name,
                "color": a.color,
                "description": a.description,
                "ability_count": a.ability_count,
            }
            for a in abilities
        ],
    }


# --- Item management ---


@router.post("/games/{game_id}/items/definitions")
async def create_item_definition(
    game_id: str,
    body: CreateItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Create an item definition. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    item_def = await inventory.create_item_definition(
        db,
        game_id=game_id,
        name=body.name,
        description=body.description,
        item_type=body.item_type,
        effect=body.effect,
        stackable=body.stackable,
    )
    return {
        "id": item_def.id,
        "name": item_def.name,
        "item_type": item_def.item_type,
        "stackable": item_def.stackable,
    }


@router.get("/games/{game_id}/items/definitions")
async def list_item_definitions(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List item definitions in a game."""
    items = await inventory.get_item_definitions(db, game_id)
    return {
        "game_id": game_id,
        "items": [
            {
                "id": i.id,
                "name": i.name,
                "description": i.description,
                "item_type": i.item_type,
                "effect": json.loads(i.effect_json) if i.effect_json else None,
                "stackable": i.stackable,
            }
            for i in items
        ],
    }


@router.post("/games/{game_id}/items/grant")
async def grant_item(
    game_id: str,
    body: GrantItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """Grant item(s) to a patient. DM only."""
    acting_user_id = user_id or current_user.id
    try:
        await permissions.require_dm(db, game_id, acting_user_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        pi = await inventory.grant_item(
            db,
            patient_id=body.patient_id,
            item_def_id=body.item_def_id,
            count=body.count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "patient_id": pi.patient_id,
        "item_def_id": pi.item_def_id,
        "count": pi.count,
    }


@router.get("/games/{game_id}/items/inventory")
async def list_inventory(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: str | None = None,
) -> dict:
    """List a player's inventory for their active character."""
    acting_user_id = user_id or current_user.id

    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == acting_user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is None or gp.active_patient_id is None:
        raise HTTPException(status_code=400, detail="No active character in this game")

    items = await inventory.get_inventory(db, gp.active_patient_id)
    return {
        "patient_id": gp.active_patient_id,
        "inventory": [
            {
                "id": i.id,
                "item_def_id": i.item_def_id,
                "count": i.count,
            }
            for i in items
        ],
    }


# --- Location queries ---


@router.get("/locations/{location_id}/players")
async def list_players_at_location(
    location_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List patients at a specific location."""
    result = await db.execute(
        select(Patient).where(Patient.current_location_id == location_id)
    )
    patients = list(result.scalars().all())
    return {
        "location_id": location_id,
        "players": [
            {
                "patient_id": p.id,
                "name": p.name,
                "soul_color": p.soul_color,
                "user_id": p.user_id,
            }
            for p in patients
        ],
    }
