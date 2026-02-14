"""Character management — Patient and Ghost CRUD, CMYK attributes."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import ColorFragment, GamePlayer, Ghost, Patient, PrintAbility

_DEFAULT_ARCHIVE_UNLOCK = '{"C":false,"M":false,"Y":false,"K":false}'


# --- Patient ---

async def create_patient(
    db: AsyncSession,
    user_id: str,
    game_id: str,
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
        user_id=user_id,
        game_id=game_id,
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

    # Auto-activate if this is the player's first patient in the game
    gp_result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = gp_result.scalar_one_or_none()
    if gp is not None and gp.role == "PL" and gp.active_patient_id is None:
        gp.active_patient_id = patient.id
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
    origin_patient_id: str,
    creator_user_id: str,
    game_id: str,
    name: str,
    soul_color: str,
    appearance: str | None = None,
    personality: str | None = None,
    initial_hp: int = 10,
) -> Ghost:
    # Fetch origin patient for snapshot
    origin = await get_patient(db, origin_patient_id)
    if origin is None:
        raise ValueError(f"Origin patient {origin_patient_id} not found")

    # Initialize CMYK: soul_color starts at 1, others at 0
    cmyk = {"C": 0, "M": 0, "Y": 0, "K": 0}
    cmyk[soul_color.upper()] = 1

    # Initialize archive unlock — soul_color archive unlocked at creation (SWAP reveals it)
    archive_unlock = {"C": False, "M": False, "Y": False, "K": False}
    archive_unlock[soul_color.upper()] = True

    ghost = Ghost(
        current_patient_id=None,  # companion assigned later via admin
        origin_patient_id=origin_patient_id,
        creator_user_id=creator_user_id,
        game_id=game_id,
        name=name,
        appearance=appearance,
        personality=personality,
        cmyk_json=json.dumps(cmyk),
        hp=initial_hp,
        hp_max=initial_hp,
        # Origin data snapshot
        origin_name=origin.name,
        origin_identity=origin.identity,
        origin_soul_color=origin.soul_color,
        origin_ideal_projection=origin.ideal_projection,
        origin_archives_json=origin.personality_archives_json,
        archive_unlock_json=json.dumps(archive_unlock),
        origin_name_unlocked=False,
        origin_identity_unlocked=False,
    )
    db.add(ghost)
    await db.flush()
    return ghost


async def get_ghost(db: AsyncSession, ghost_id: str) -> Ghost | None:
    result = await db.execute(select(Ghost).where(Ghost.id == ghost_id))
    return result.scalar_one_or_none()


async def get_ghosts_in_game(db: AsyncSession, game_id: str) -> list[Ghost]:
    result = await db.execute(select(Ghost).where(Ghost.game_id == game_id))
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
) -> dict:
    """Apply a color fragment: increment the CMYK value and record the fragment.

    Returns dict with updated cmyk and fragment_id (usable as archive unlock key).
    """
    cmyk = get_cmyk(ghost)
    old_val = cmyk.get(color.upper(), 0)
    cmyk[color.upper()] = old_val + value
    ghost.cmyk_json = json.dumps(cmyk)

    fragment = ColorFragment(
        game_id=ghost.game_id,
        holder_ghost_id=ghost.id,
        color=color.upper(),
        value=float(value),
    )
    db.add(fragment)
    await db.flush()
    return {"cmyk": cmyk, "fragment_id": fragment.id}


async def unlock_archive(db: AsyncSession, fragment_id: str, ghost_id: str) -> dict:
    """Redeem a color fragment to unlock the corresponding origin archive.

    Returns dict with the unlocked color and archive content.
    """
    from datetime import datetime, timezone

    result = await db.execute(
        select(ColorFragment).where(ColorFragment.id == fragment_id)
    )
    fragment = result.scalar_one_or_none()
    if fragment is None:
        raise ValueError(f"Fragment {fragment_id} not found")
    if fragment.holder_ghost_id != ghost_id:
        raise ValueError("Fragment does not belong to this ghost")
    if fragment.redeemed:
        raise ValueError("Fragment has already been redeemed")

    ghost = await get_ghost(db, ghost_id)
    if ghost is None:
        raise ValueError(f"Ghost {ghost_id} not found")

    color = fragment.color.upper()
    unlock_state = json.loads(ghost.archive_unlock_json)
    if unlock_state.get(color, False):
        raise ValueError(f"Archive for color {color} is already unlocked")

    # Mark fragment as redeemed
    fragment.redeemed = True
    fragment.redeemed_at = datetime.now(timezone.utc)

    # Unlock the archive
    unlock_state[color] = True
    ghost.archive_unlock_json = json.dumps(unlock_state)
    await db.flush()

    # Return the unlocked archive content
    archives = json.loads(ghost.origin_archives_json) if ghost.origin_archives_json else {}
    return {
        "color": color,
        "archive_content": archives.get(color),
        "archive_unlock_state": unlock_state,
    }


def get_unlocked_origin_data(ghost: Ghost) -> dict:
    """Return origin patient data filtered by unlock state.

    soul_color and ideal_projection are always visible (shared via SWAP).
    Archives are gated by archive_unlock_json.
    Name/identity are gated by explicit unlock flags.
    """
    result: dict = {
        "origin_soul_color": ghost.origin_soul_color,
        "origin_ideal_projection": ghost.origin_ideal_projection,
    }
    if ghost.origin_name_unlocked:
        result["origin_name"] = ghost.origin_name
    if ghost.origin_identity_unlocked:
        result["origin_identity"] = ghost.origin_identity

    unlock_state = json.loads(ghost.archive_unlock_json) if ghost.archive_unlock_json else {}
    archives = json.loads(ghost.origin_archives_json) if ghost.origin_archives_json else {}
    result["origin_archives"] = {
        color: archives.get(color)
        for color, unlocked in unlock_state.items()
        if unlocked and archives.get(color) is not None
    }
    return result


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
