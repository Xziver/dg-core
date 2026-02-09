"""Character management — Patient and Ghost CRUD, CMYK attributes."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import ColorFragment, Ghost, Patient, PrintAbility


# --- Patient ---

async def create_patient(
    db: AsyncSession,
    player_id: str,
    session_id: str,
    name: str,
    soul_color: str,
    gender: str | None = None,
    age: int | None = None,
    identity: str | None = None,
    portrait_url: str | None = None,
    personality_archives: dict | None = None,
    ideal_projection: str | None = None,
) -> Patient:
    patient = Patient(
        player_id=player_id,
        session_id=session_id,
        name=name,
        soul_color=soul_color.upper(),
        gender=gender,
        age=age,
        identity=identity,
        portrait_url=portrait_url,
        personality_archives_json=json.dumps(personality_archives) if personality_archives else None,
        ideal_projection=ideal_projection,
    )
    db.add(patient)
    await db.flush()
    return patient


async def get_patient(db: AsyncSession, patient_id: str) -> Patient | None:
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    return result.scalar_one_or_none()


def generate_swap_file(patient: Patient) -> dict:
    """Generate the SWAP file for ghost creation: soul_color + ideal_projection + one archive entry."""
    archives = json.loads(patient.personality_archives_json) if patient.personality_archives_json else {}
    # SWAP reveals only the soul_color archive
    revealed_archive = {}
    color_key = patient.soul_color.upper()
    if color_key in archives:
        revealed_archive[color_key] = archives[color_key]

    return {
        "type": "SWAP",
        "soul_color": patient.soul_color,
        "ideal_projection": patient.ideal_projection,
        "revealed_archive": revealed_archive,
    }


# --- Ghost ---

async def create_ghost(
    db: AsyncSession,
    patient_id: str,
    creator_player_id: str,
    session_id: str,
    name: str,
    soul_color: str,
    appearance: str | None = None,
    personality: str | None = None,
    initial_hp: int = 10,
) -> Ghost:
    # Initialize CMYK: soul_color starts at 1, others at 0
    cmyk = {"C": 0, "M": 0, "Y": 0, "K": 0}
    cmyk[soul_color.upper()] = 1

    ghost = Ghost(
        patient_id=patient_id,
        creator_player_id=creator_player_id,
        session_id=session_id,
        name=name,
        appearance=appearance,
        personality=personality,
        cmyk_json=json.dumps(cmyk),
        hp=initial_hp,
        hp_max=initial_hp,
    )
    db.add(ghost)
    await db.flush()
    return ghost


async def get_ghost(db: AsyncSession, ghost_id: str) -> Ghost | None:
    result = await db.execute(select(Ghost).where(Ghost.id == ghost_id))
    return result.scalar_one_or_none()


async def get_ghosts_in_session(db: AsyncSession, session_id: str) -> list[Ghost]:
    result = await db.execute(select(Ghost).where(Ghost.session_id == session_id))
    return list(result.scalars().all())


def get_cmyk(ghost: Ghost) -> dict[str, int]:
    return json.loads(ghost.cmyk_json)


def get_color_value(ghost: Ghost, color: str) -> int:
    cmyk = get_cmyk(ghost)
    return cmyk.get(color.upper(), 0)


async def set_color_value(db: AsyncSession, ghost: Ghost, color: str, value: int) -> None:
    cmyk = get_cmyk(ghost)
    cmyk[color.upper()] = max(0, value)
    ghost.cmyk_json = json.dumps(cmyk)
    await db.flush()


async def apply_color_fragment(
    db: AsyncSession, ghost: Ghost, color: str, value: int = 1
) -> dict[str, int]:
    """Apply a color fragment: increment the CMYK value and record the fragment."""
    cmyk = get_cmyk(ghost)
    old_val = cmyk.get(color.upper(), 0)
    cmyk[color.upper()] = old_val + value
    ghost.cmyk_json = json.dumps(cmyk)

    fragment = ColorFragment(
        session_id=ghost.session_id,
        holder_ghost_id=ghost.id,
        color=color.upper(),
        value=float(value),
    )
    db.add(fragment)
    await db.flush()
    return cmyk


async def change_hp(db: AsyncSession, ghost: Ghost, delta: int) -> tuple[int, bool]:
    """Change ghost HP. Returns (new_hp, collapsed)."""
    ghost.hp = max(0, min(ghost.hp + delta, ghost.hp_max))
    collapsed = ghost.hp <= 0
    await db.flush()
    return ghost.hp, collapsed


# --- Print Abilities ---

async def add_print_ability(
    db: AsyncSession,
    ghost_id: str,
    name: str,
    color: str,
    description: str | None = None,
    ability_count: int = 1,
) -> PrintAbility:
    ability = PrintAbility(
        ghost_id=ghost_id,
        name=name,
        description=description,
        color=color.upper(),
        ability_count=ability_count,
    )
    db.add(ability)
    await db.flush()
    return ability


async def get_print_abilities(db: AsyncSession, ghost_id: str) -> list[PrintAbility]:
    result = await db.execute(
        select(PrintAbility).where(PrintAbility.ghost_id == ghost_id)
    )
    return list(result.scalars().all())


async def get_print_ability(db: AsyncSession, ability_id: str) -> PrintAbility | None:
    result = await db.execute(select(PrintAbility).where(PrintAbility.id == ability_id))
    return result.scalar_one_or_none()


async def use_print_ability(db: AsyncSession, ability: PrintAbility) -> bool:
    """Consume one use of a print ability. Returns True if successful."""
    if ability.ability_count <= 0:
        return False
    ability.ability_count -= 1
    await db.flush()
    return True
