"""Admin API — session and character management."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, session as session_mod
from app.infra.db import get_db
from app.modules.rag.index import index_document

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Request schemas ---

class CreateSessionRequest(BaseModel):
    name: str
    created_by: str  # player_id
    config: dict | None = None


class UpdateSessionRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    config: dict | None = None


class AddPlayerRequest(BaseModel):
    player_id: str
    role: str = "PL"


class CreatePatientRequest(BaseModel):
    player_id: str
    session_id: str
    name: str
    soul_color: str
    gender: str | None = None
    age: int | None = None
    identity: str | None = None
    portrait_url: str | None = None
    personality_archives: dict | None = None
    ideal_projection: str | None = None


class CreateGhostRequest(BaseModel):
    patient_id: str
    creator_player_id: str
    session_id: str
    name: str
    soul_color: str
    appearance: str | None = None
    personality: str | None = None
    initial_hp: int = 10
    print_abilities: list[PrintAbilityInput] | None = None


class PrintAbilityInput(BaseModel):
    name: str
    color: str
    description: str | None = None
    ability_count: int = 1


# Fix forward reference
CreateGhostRequest.model_rebuild()


class CreatePlayerRequest(BaseModel):
    platform: str
    platform_uid: str
    display_name: str


class RAGUploadRequest(BaseModel):
    content: str
    category: str
    metadata: dict | None = None


# --- Endpoints ---

@router.post("/players")
async def create_player(
    req: CreatePlayerRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    import hashlib
    import secrets
    from app.models.db_models import Player

    api_key = secrets.token_hex(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    player = Player(
        platform=req.platform,
        platform_uid=req.platform_uid,
        display_name=req.display_name,
        api_key_hash=api_key_hash,
    )
    db.add(player)
    await db.flush()
    return {"player_id": player.id, "api_key": api_key}


@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    s = await session_mod.create_session(db, req.name, req.created_by, req.config)
    return {"session_id": s.id, "name": s.name, "status": s.status}


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    req: UpdateSessionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    s = await session_mod.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.name is not None:
        s.name = req.name
    if req.status is not None:
        s.status = req.status
    if req.config is not None:
        s.config_json = json.dumps(req.config)
    await db.flush()
    return {"session_id": s.id, "name": s.name, "status": s.status}


@router.post("/sessions/{session_id}/players")
async def add_player_to_session(
    session_id: str,
    req: AddPlayerRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    link = await session_mod.join_session(db, session_id, req.player_id, req.role)
    return {"session_id": session_id, "player_id": req.player_id, "role": link.role}


@router.post("/characters/patient")
async def create_patient(
    req: CreatePatientRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patient = await character.create_patient(
        db,
        player_id=req.player_id,
        session_id=req.session_id,
        name=req.name,
        soul_color=req.soul_color,
        gender=req.gender,
        age=req.age,
        identity=req.identity,
        portrait_url=req.portrait_url,
        personality_archives=req.personality_archives,
        ideal_projection=req.ideal_projection,
    )
    swap = character.generate_swap_file(patient)
    return {"patient_id": patient.id, "name": patient.name, "swap_file": swap}


@router.post("/characters/ghost")
async def create_ghost(
    req: CreateGhostRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.create_ghost(
        db,
        patient_id=req.patient_id,
        creator_player_id=req.creator_player_id,
        session_id=req.session_id,
        name=req.name,
        soul_color=req.soul_color,
        appearance=req.appearance,
        personality=req.personality,
        initial_hp=req.initial_hp,
    )

    # Add print abilities if provided
    abilities = []
    if req.print_abilities:
        for pa in req.print_abilities:
            ability = await character.add_print_ability(
                db, ghost.id, pa.name, pa.color, pa.description, pa.ability_count
            )
            abilities.append({"id": ability.id, "name": ability.name, "color": ability.color})

    return {
        "ghost_id": ghost.id,
        "name": ghost.name,
        "cmyk": json.loads(ghost.cmyk_json),
        "hp": ghost.hp,
        "hp_max": ghost.hp_max,
        "print_abilities": abilities,
    }


@router.get("/characters/{character_id}")
async def get_character(
    character_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Try ghost first, then patient
    ghost = await character.get_ghost(db, character_id)
    if ghost:
        abilities = await character.get_print_abilities(db, ghost.id)
        return {
            "type": "ghost",
            "id": ghost.id,
            "name": ghost.name,
            "cmyk": json.loads(ghost.cmyk_json),
            "hp": ghost.hp,
            "hp_max": ghost.hp_max,
            "appearance": ghost.appearance,
            "personality": ghost.personality,
            "print_abilities": [
                {"id": a.id, "name": a.name, "color": a.color, "ability_count": a.ability_count}
                for a in abilities
            ],
        }

    patient = await character.get_patient(db, character_id)
    if patient:
        return {
            "type": "patient",
            "id": patient.id,
            "name": patient.name,
            "soul_color": patient.soul_color,
            "gender": patient.gender,
            "age": patient.age,
            "identity": patient.identity,
        }

    raise HTTPException(status_code=404, detail="Character not found")


@router.post("/rag/upload")
async def upload_rag_document(req: RAGUploadRequest) -> dict:
    chunks = await index_document(req.content, req.category, req.metadata)
    return {"chunks_indexed": chunks, "category": req.category}
