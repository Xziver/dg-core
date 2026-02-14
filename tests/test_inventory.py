"""Tests for the item and inventory system."""

import pytest

from app.domain.inventory import (
    create_item_definition,
    get_inventory,
    get_item_definitions,
    grant_item,
    use_item,
)
from app.models.db_models import Game, Ghost, Patient, User


async def _setup_game_with_ghost(db):
    """Helper: create user, game, patient, ghost for inventory tests."""
    user = User(username=f"inv_user_{id(db)}")
    db.add(user)
    await db.flush()

    game = Game(name="InvGame", created_by=user.id)
    db.add(game)
    await db.flush()

    patient = Patient(
        user_id=user.id, game_id=game.id, name="InvPatient", soul_color="C"
    )
    db.add(patient)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="InvGhost",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}',
        hp=8, hp_max=10, mp=3, mp_max=5,
        current_patient_id=patient.id,
    )
    db.add(ghost)
    await db.flush()

    return user, game, patient, ghost


@pytest.mark.asyncio
async def test_create_item_definition(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(
        db, game.id, "Health Potion",
        description="Restores 3 HP",
        item_type="consumable",
        effect={"type": "heal_hp", "value": 3},
    )
    assert item_def.name == "Health Potion"
    assert item_def.stackable is True

    defs = await get_item_definitions(db, game.id)
    assert len(defs) == 1


@pytest.mark.asyncio
async def test_grant_item(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(db, game.id, "Coin")
    pi = await grant_item(db, patient.id, item_def.id, count=5)
    assert pi.count == 5

    inv = await get_inventory(db, patient.id)
    assert len(inv) == 1
    assert inv[0].count == 5


@pytest.mark.asyncio
async def test_grant_item_stacks(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(db, game.id, "Arrow", stackable=True)
    await grant_item(db, patient.id, item_def.id, count=10)
    await grant_item(db, patient.id, item_def.id, count=5)

    inv = await get_inventory(db, patient.id)
    assert len(inv) == 1
    assert inv[0].count == 15


@pytest.mark.asyncio
async def test_grant_item_non_stackable(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    # Non-stackable: same definition can't be granted twice (unique constraint)
    # Instead grant two different items
    item_def1 = await create_item_definition(db, game.id, "Key A", stackable=False)
    item_def2 = await create_item_definition(db, game.id, "Key B", stackable=False)
    await grant_item(db, patient.id, item_def1.id, count=1)
    await grant_item(db, patient.id, item_def2.id, count=1)

    inv = await get_inventory(db, patient.id)
    assert len(inv) == 2  # Two separate entries


@pytest.mark.asyncio
async def test_use_item_heal_hp(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(
        db, game.id, "Heal Potion",
        effect={"type": "heal_hp", "value": 5},
    )
    await grant_item(db, patient.id, item_def.id, count=2)

    result = await use_item(db, game.id, patient.id, item_def.id, ghost)
    assert result.success is True
    assert ghost.hp == 10  # Was 8, healed 5, capped at hp_max=10
    assert result.data["heal_hp"] == 2  # Only healed 2 (8+5 capped at 10)

    # Check count decreased
    inv = await get_inventory(db, patient.id)
    assert inv[0].count == 1


@pytest.mark.asyncio
async def test_use_item_heal_mp(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(
        db, game.id, "Mana Potion",
        effect={"type": "heal_mp", "value": 10},
    )
    await grant_item(db, patient.id, item_def.id, count=1)

    result = await use_item(db, game.id, patient.id, item_def.id, ghost)
    assert result.success is True
    assert ghost.mp == 5  # Was 3, healed 10, capped at mp_max=5

    # Item consumed — inventory should be empty
    inv = await get_inventory(db, patient.id)
    assert len(inv) == 0


@pytest.mark.asyncio
async def test_use_item_not_in_inventory(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    item_def = await create_item_definition(db, game.id, "Nothing")

    result = await use_item(db, game.id, patient.id, item_def.id, ghost)
    assert result.success is False
    assert "not in inventory" in result.error.lower()


@pytest.mark.asyncio
async def test_use_item_apply_buff(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain.buff import get_buffs

    item_def = await create_item_definition(
        db, game.id, "Shield Scroll",
        effect={
            "type": "apply_buff",
            "buff_name": "Magic Shield",
            "expression": "+2",
            "duration": 3,
        },
    )
    await grant_item(db, patient.id, item_def.id, count=1)

    result = await use_item(db, game.id, patient.id, item_def.id, ghost)
    assert result.success is True
    assert result.data["buff_applied"] == "Magic Shield"

    buffs = await get_buffs(db, ghost.id)
    assert len(buffs) == 1
    assert buffs[0].name == "Magic Shield"
    assert buffs[0].remaining_rounds == 3
