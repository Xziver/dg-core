"""Tests for the buff/debuff system."""

import pytest

from app.domain.buff import (
    add_buff,
    classify_expression,
    compute_buff_modifier,
    get_buffs,
    remove_buff,
    remove_buff_by_name,
    tick_buffs,
)
from app.models.db_models import Game, Ghost, Patient, User


@pytest.mark.asyncio
async def test_classify_numeric(db_session):
    assert classify_expression("+3") == "numeric"
    assert classify_expression("-1") == "numeric"
    assert classify_expression("5") == "numeric"


@pytest.mark.asyncio
async def test_classify_attribute(db_session):
    assert classify_expression("c+2") == "attribute"
    assert classify_expression("M") == "attribute"
    assert classify_expression("k-1") == "attribute"


@pytest.mark.asyncio
async def test_classify_dice(db_session):
    assert classify_expression("1d6") == "dice"
    assert classify_expression("2d6+3") == "dice"


@pytest.mark.asyncio
async def test_classify_text(db_session):
    assert classify_expression("some_status") == "text"


@pytest.mark.asyncio
async def test_add_and_get_buff(db_session):
    db = db_session
    user = User(username="buff_user")
    db.add(user)
    await db.flush()

    game = Game(name="BuffGame", created_by=user.id)
    db.add(game)
    await db.flush()

    patient = Patient(user_id=user.id, game_id=game.id, name="P", soul_color="C")
    db.add(patient)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="G",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}', hp=10, hp_max=10,
    )
    db.add(ghost)
    await db.flush()

    buff = await add_buff(db, ghost.id, game.id, "Shield", "+3", remaining_rounds=2, created_by=user.id)
    assert buff.name == "Shield"
    assert buff.buff_type == "numeric"
    assert buff.remaining_rounds == 2

    buffs = await get_buffs(db, ghost.id)
    assert len(buffs) == 1


@pytest.mark.asyncio
async def test_remove_buff(db_session):
    db = db_session
    user = User(username="rm_buff_user")
    db.add(user)
    await db.flush()

    game = Game(name="RmBuffGame", created_by=user.id)
    db.add(game)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="G2",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}', hp=10, hp_max=10,
    )
    db.add(ghost)
    await db.flush()

    buff = await add_buff(db, ghost.id, game.id, "Temp", "+1", created_by=user.id)
    await remove_buff(db, buff.id)

    buffs = await get_buffs(db, ghost.id)
    assert len(buffs) == 0


@pytest.mark.asyncio
async def test_remove_buff_by_name(db_session):
    db = db_session
    user = User(username="rm_name_user")
    db.add(user)
    await db.flush()

    game = Game(name="RmNameGame", created_by=user.id)
    db.add(game)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="G3",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}', hp=10, hp_max=10,
    )
    db.add(ghost)
    await db.flush()

    await add_buff(db, ghost.id, game.id, "Named", "+2", created_by=user.id)
    await remove_buff_by_name(db, ghost.id, "Named")

    buffs = await get_buffs(db, ghost.id)
    assert len(buffs) == 0


@pytest.mark.asyncio
async def test_tick_buffs_expires(db_session):
    db = db_session
    user = User(username="tick_user")
    db.add(user)
    await db.flush()

    game = Game(name="TickGame", created_by=user.id)
    db.add(game)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="G4",
        cmyk_json='{"C":1,"M":0,"Y":0,"K":0}', hp=10, hp_max=10,
    )
    db.add(ghost)
    await db.flush()

    await add_buff(db, ghost.id, game.id, "Short", "+1", remaining_rounds=1, created_by=user.id)
    await add_buff(db, ghost.id, game.id, "Perm", "+2", remaining_rounds=-1, created_by=user.id)

    expired = await tick_buffs(db, ghost.id)
    assert "Short" in expired

    buffs = await get_buffs(db, ghost.id)
    assert len(buffs) == 1
    assert buffs[0].name == "Perm"


def test_compute_buff_modifier_numeric():
    from types import SimpleNamespace
    buff = SimpleNamespace(buff_type="numeric", expression="+3")

    cmyk_adj, flat_mod = compute_buff_modifier([buff], {"C": 1, "M": 0, "Y": 0, "K": 0})
    assert flat_mod == 3
    assert cmyk_adj == {"C": 0, "M": 0, "Y": 0, "K": 0}


def test_compute_buff_modifier_attribute():
    from types import SimpleNamespace
    buff = SimpleNamespace(buff_type="attribute", expression="c+2")

    cmyk_adj, flat_mod = compute_buff_modifier([buff], {"C": 1, "M": 0, "Y": 0, "K": 0})
    assert flat_mod == 0
    assert cmyk_adj["C"] == 2
