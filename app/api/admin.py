"""Admin API — game, region, location, and character management."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character, game as game_mod, region as region_mod
from app.infra.auth import get_current_user
from app.infra.db import get_db
from app.models.db_models import User
from app.modules.rag.index import index_document

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Request schemas ---

class CreateGameRequest(BaseModel):
    name: str
    config: dict | None = None


class UpdateGameRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    config: dict | None = None


class AddPlayerRequest(BaseModel):
    user_id: str
    role: str = "PL"


class CreateRegionRequest(BaseModel):
    code: str
    name: str
    description: str | None = None
    metadata: dict | None = None
    sort_order: int = 0


class CreateLocationRequest(BaseModel):
    name: str
    description: str | None = None
    content: str | None = None
    metadata: dict | None = None
    sort_order: int = 0


class CreatePatientRequest(BaseModel):
    user_id: str
    game_id: str
    name: str
    soul_color: str
    gender: str | None = None
    age: int | None = None
    identity: str | None = None
    portrait_url: str | None = None
    personality_archives: dict | None = None
    ideal_projection: str | None = None


class CreateGhostRequest(BaseModel):
    origin_patient_id: str
    creator_user_id: str
    game_id: str
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


class RAGUploadRequest(BaseModel):
    content: str
    category: str
    metadata: dict | None = None


# --- Game endpoints ---

@router.post("/games")
async def create_game(
    req: CreateGameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    game = await game_mod.create_game(db, req.name, current_user.id, req.config)
    return {"game_id": game.id, "name": game.name, "status": game.status}


@router.put("/games/{game_id}")
async def update_game(
    game_id: str,
    req: UpdateGameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    game = await game_mod.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    if req.name is not None:
        game.name = req.name
    if req.status is not None:
        game.status = req.status
    if req.config is not None:
        game.config_json = json.dumps(req.config)
    await db.flush()
    return {"game_id": game.id, "name": game.name, "status": game.status}


@router.post("/games/{game_id}/players")
async def add_player_to_game(
    game_id: str,
    req: AddPlayerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    link = await game_mod.join_game(db, game_id, req.user_id, req.role)
    return {"game_id": game_id, "user_id": req.user_id, "role": link.role}


# --- Region endpoints ---

@router.post("/games/{game_id}/regions")
async def create_region(
    game_id: str,
    req: CreateRegionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    region = await region_mod.create_region(
        db, game_id=game_id, name=req.name, code=req.code,
        description=req.description, metadata=req.metadata, sort_order=req.sort_order,
    )
    return {
        "region_id": region.id, "game_id": game_id,
        "code": region.code, "name": region.name,
    }


@router.get("/games/{game_id}/regions")
async def list_regions(
    game_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    regions = await region_mod.get_regions(db, game_id)
    return {
        "game_id": game_id,
        "regions": [
            {"id": r.id, "code": r.code, "name": r.name, "description": r.description}
            for r in regions
        ],
    }


# --- Location endpoints ---

@router.post("/regions/{region_id}/locations")
async def create_location(
    region_id: str,
    req: CreateLocationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    location = await region_mod.create_location(
        db, region_id=region_id, name=req.name,
        description=req.description, content=req.content,
        metadata=req.metadata, sort_order=req.sort_order,
    )
    return {
        "location_id": location.id, "region_id": region_id,
        "name": location.name,
    }


@router.get("/regions/{region_id}/locations")
async def list_locations(
    region_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    locations = await region_mod.get_locations(db, region_id)
    return {
        "region_id": region_id,
        "locations": [
            {"id": loc.id, "name": loc.name, "description": loc.description}
            for loc in locations
        ],
    }


# --- Character endpoints ---

@router.post("/characters/patient")
async def create_patient(
    req: CreatePatientRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    patient = await character.create_patient(
        db,
        user_id=req.user_id,
        game_id=req.game_id,
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
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    ghost = await character.create_ghost(
        db,
        origin_patient_id=req.origin_patient_id,
        creator_user_id=req.creator_user_id,
        game_id=req.game_id,
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
        "origin_snapshot": {
            "origin_name": ghost.origin_name,
            "origin_soul_color": ghost.origin_soul_color,
            "origin_identity": ghost.origin_identity,
            "origin_ideal_projection": ghost.origin_ideal_projection,
            "archive_unlock_state": json.loads(ghost.archive_unlock_json),
        },
    }


@router.get("/characters/{character_id}")
async def get_character(
    character_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
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
            "current_patient_id": ghost.current_patient_id,
            "origin_patient_id": ghost.origin_patient_id,
            "origin_snapshot": {
                "origin_name": ghost.origin_name,
                "origin_identity": ghost.origin_identity,
                "origin_soul_color": ghost.origin_soul_color,
                "origin_ideal_projection": ghost.origin_ideal_projection,
                "origin_archives": json.loads(ghost.origin_archives_json) if ghost.origin_archives_json else None,
            },
            "unlock_state": {
                "archive_unlock": json.loads(ghost.archive_unlock_json),
                "origin_name_unlocked": ghost.origin_name_unlocked,
                "origin_identity_unlocked": ghost.origin_identity_unlocked,
            },
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


class AssignCompanionRequest(BaseModel):
    patient_id: str


@router.put("/characters/ghost/{ghost_id}/assign-companion")
async def assign_ghost_companion(
    ghost_id: str,
    req: AssignCompanionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Assign a ghost as companion to a patient (admin operation)."""
    ghost = await character.get_ghost(db, ghost_id)
    if ghost is None:
        raise HTTPException(status_code=404, detail="Ghost not found")
    ghost.current_patient_id = req.patient_id
    await db.flush()
    return {
        "ghost_id": ghost.id,
        "current_patient_id": ghost.current_patient_id,
    }


# --- RAG endpoint ---

@router.post("/rag/upload")
async def upload_rag_document(
    req: RAGUploadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    chunks = await index_document(req.content, req.category, req.metadata)
    return {"chunks_indexed": chunks, "category": req.category}
