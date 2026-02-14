"""Tests for the communication system."""

import pytest

from app.domain import character
from app.domain.communication import (
    accept_communication,
    cancel_communication,
    get_pending_requests,
    reject_communication,
    request_communication,
)
from app.models.db_models import Game, GamePlayer, Ghost, Patient, User


async def _setup_two_players(db):
    """Helper: create two users with patients and ghosts for communication tests."""
    user1 = User(username=f"comm_u1_{id(db)}")
    user2 = User(username=f"comm_u2_{id(db)}")
    db.add_all([user1, user2])
    await db.flush()

    game = Game(name="CommGame", created_by=user1.id)
    db.add(game)
    await db.flush()

    gp1 = GamePlayer(game_id=game.id, user_id=user1.id, role="PL")
    gp2 = GamePlayer(game_id=game.id, user_id=user2.id, role="PL")
    db.add_all([gp1, gp2])
    await db.flush()

    # Patient 1: soul_color C
    patient1 = Patient(
        user_id=user1.id, game_id=game.id, name="P1", soul_color="C"
    )
    # Patient 2: soul_color M
    patient2 = Patient(
        user_id=user2.id, game_id=game.id, name="P2", soul_color="M"
    )
    db.add_all([patient1, patient2])
    await db.flush()

    # Ghost 1: has C=2, M=1 (can communicate with M-soul targets)
    ghost1 = Ghost(
        game_id=game.id, creator_user_id=user2.id, name="G1",
        cmyk_json='{"C":2,"M":1,"Y":0,"K":0}',
        hp=10, hp_max=10, mp=5, mp_max=5,
        current_patient_id=patient1.id,
    )
    # Ghost 2: has C=0, M=2 (can communicate with C-soul? no, C=0)
    ghost2 = Ghost(
        game_id=game.id, creator_user_id=user1.id, name="G2",
        cmyk_json='{"C":0,"M":2,"Y":0,"K":0}',
        hp=10, hp_max=10, mp=5, mp_max=5,
        current_patient_id=patient2.id,
    )
    db.add_all([ghost1, ghost2])
    await db.flush()

    gp1.active_patient_id = patient1.id
    gp2.active_patient_id = patient2.id
    await db.flush()

    return game, user1, user2, patient1, patient2, ghost1, ghost2


@pytest.mark.asyncio
async def test_request_communication_success(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    # Ghost1 has M=1, patient2's soul_color is M → should succeed
    comm = await request_communication(db, game.id, p1.id, p2.id)
    assert comm.status == "pending"
    assert comm.initiator_patient_id == p1.id
    assert comm.target_patient_id == p2.id
    # MP should be deducted
    assert g1.mp == 4


@pytest.mark.asyncio
async def test_request_communication_no_mp(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    # Drain MP
    g1.mp = 0
    await db.flush()

    with pytest.raises(ValueError, match="Not enough MP"):
        await request_communication(db, game.id, p1.id, p2.id)


@pytest.mark.asyncio
async def test_request_communication_wrong_color(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    # Ghost2 has C=0, patient1's soul_color is C → should fail
    with pytest.raises(ValueError, match="value is 0"):
        await request_communication(db, game.id, p2.id, p1.id)


@pytest.mark.asyncio
async def test_request_communication_duplicate_blocked(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    await request_communication(db, game.id, p1.id, p2.id)

    with pytest.raises(ValueError, match="already exists"):
        await request_communication(db, game.id, p1.id, p2.id)


@pytest.mark.asyncio
async def test_accept_communication(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    # Add an ability to ghost2 (target) for transfer
    await character.add_print_ability(db, g2.id, "TargetAbility", "M")

    comm = await request_communication(db, game.id, p1.id, p2.id)
    result = await accept_communication(db, comm.id)

    assert result["status"] == "accepted"
    assert result["transferred_ability"]["name"] == "TargetAbility"
    assert "initiator_info" in result
    assert "target_info" in result

    # Verify ability was cloned to ghost1
    g1_abilities = await character.get_print_abilities(db, g1.id)
    assert any(a.name == "TargetAbility" for a in g1_abilities)


@pytest.mark.asyncio
async def test_reject_communication(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    comm = await request_communication(db, game.id, p1.id, p2.id)
    rejected = await reject_communication(db, comm.id)
    assert rejected.status == "rejected"


@pytest.mark.asyncio
async def test_cancel_communication(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    comm = await request_communication(db, game.id, p1.id, p2.id)
    cancelled = await cancel_communication(db, comm.id)
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_get_pending_requests(db_session):
    db = db_session
    game, u1, u2, p1, p2, g1, g2 = await _setup_two_players(db)

    await request_communication(db, game.id, p1.id, p2.id)

    pending = await get_pending_requests(db, game.id, p2.id)
    assert len(pending) == 1
    assert pending[0].initiator_patient_id == p1.id

    # No pending for p1
    pending_p1 = await get_pending_requests(db, game.id, p1.id)
    assert len(pending_p1) == 0
