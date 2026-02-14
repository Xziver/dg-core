"""Tests for the event check system."""

import pytest

from app.domain import character
from app.domain.rules.event_check import (
    deactivate_event,
    get_active_event,
    get_active_events,
    handle_event_check,
    handle_reroll,
    set_event,
)
from app.models.db_models import Game, GamePlayer, Ghost, Patient, User


async def _setup_game_with_ghost(db):
    """Helper: create user, game, patient, ghost with CMYK {C:3, M:1, Y:0, K:0}."""
    user = User(username=f"ec_user_{id(db)}")
    db.add(user)
    await db.flush()

    game = Game(name="ECGame", created_by=user.id)
    db.add(game)
    await db.flush()

    gp = GamePlayer(game_id=game.id, user_id=user.id, role="PL")
    db.add(gp)
    await db.flush()

    patient = Patient(
        user_id=user.id, game_id=game.id, name="ECPatient", soul_color="C"
    )
    db.add(patient)
    await db.flush()

    ghost = Ghost(
        game_id=game.id, creator_user_id=user.id, name="ECGhost",
        cmyk_json='{"C":3,"M":1,"Y":0,"K":0}',
        hp=10, hp_max=10, mp=5, mp_max=5,
        current_patient_id=patient.id,
    )
    db.add(ghost)
    await db.flush()

    gp.active_patient_id = patient.id
    await db.flush()

    return user, game, patient, ghost


@pytest.mark.asyncio
async def test_set_and_get_event(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    event_def = await set_event(
        db, session.id, game.id, "Test Event", "2d6+3",
        color_restriction="C", created_by=user.id,
    )
    assert event_def.name == "Test Event"
    assert event_def.is_active is True

    found = await get_active_event(db, session.id, "Test Event")
    assert found is not None
    assert found.id == event_def.id


@pytest.mark.asyncio
async def test_deactivate_event(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "DeactEvent", "3d6", created_by=user.id)
    deactivated = await deactivate_event(db, session.id, "DeactEvent")
    assert deactivated.is_active is False

    events = await get_active_events(db, session.id)
    assert len(events) == 0


@pytest.mark.asyncio
async def test_event_check_success_flow(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "Easy", "1d6", created_by=user.id)

    result = await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "Easy", color="C",
    )
    assert result.success is True
    assert result.event_type == "event_check"
    assert "player_total" in result.data
    assert "target_total" in result.data
    assert "check_success" in result.data


@pytest.mark.asyncio
async def test_event_check_no_event(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    result = await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "NonExistent",
    )
    assert result.success is False
    assert "No active event" in result.error


@pytest.mark.asyncio
async def test_event_check_caches_target(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "Cache", "2d6", created_by=user.id)

    r1 = await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "Cache", color="C",
    )
    target_1 = r1.data["target_total"]

    r2 = await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "Cache", color="C",
    )
    target_2 = r2.data["target_total"]

    assert target_1 == target_2  # Same cached target


@pytest.mark.asyncio
async def test_reroll_same_color(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "RerollTest", "2d6", created_by=user.id)

    # Do initial check
    await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "RerollTest", color="C",
    )

    # Add ability with matching color
    ability = await character.add_print_ability(db, ghost.id, "TestAbility", "C")

    # Reroll (same color)
    result = await handle_reroll(
        db, game.id, session.id, user.id, ghost, patient,
        "RerollTest", ability.id, hard=False,
    )
    assert result.success is True
    assert result.event_type == "reroll"


@pytest.mark.asyncio
async def test_reroll_wrong_color_fails(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "ColorMismatch", "2d6",
                    color_restriction="C", created_by=user.id)

    await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "ColorMismatch",
    )

    # Ability is M but check is C
    ability = await character.add_print_ability(db, ghost.id, "MAbility", "M")

    result = await handle_reroll(
        db, game.id, session.id, user.id, ghost, patient,
        "ColorMismatch", ability.id, hard=False,
    )
    assert result.success is False
    assert "color" in result.error.lower()


@pytest.mark.asyncio
async def test_hard_reroll_costs_mp(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "HRTest", "2d6",
                    color_restriction="C", created_by=user.id)

    await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "HRTest",
    )

    old_mp = ghost.mp
    ability = await character.add_print_ability(db, ghost.id, "MAb", "M")

    result = await handle_reroll(
        db, game.id, session.id, user.id, ghost, patient,
        "HRTest", ability.id, hard=True,
    )
    assert result.success is True
    assert result.event_type == "hard_reroll"
    assert ghost.mp == old_mp - 1


@pytest.mark.asyncio
async def test_duplicate_ability_usage_blocked(db_session):
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    await set_event(db, session.id, game.id, "DupTest", "2d6", created_by=user.id)

    await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient, "DupTest", color="C",
    )

    ability = await character.add_print_ability(db, ghost.id, "Dup", "C", ability_count=2)

    # First reroll should succeed
    r1 = await handle_reroll(
        db, game.id, session.id, user.id, ghost, patient,
        "DupTest", ability.id, hard=False,
    )
    assert r1.success is True

    # Second reroll with same ability should fail
    r2 = await handle_reroll(
        db, game.id, session.id, user.id, ghost, patient,
        "DupTest", ability.id, hard=False,
    )
    assert r2.success is False
    assert "already been used" in r2.error


@pytest.mark.asyncio
async def test_color_resolution_priority(db_session):
    """Event color_restriction > player choice > soul_color."""
    db = db_session
    user, game, patient, ghost = await _setup_game_with_ghost(db)

    from app.domain import session as session_mod
    session = await session_mod.start_session(db, game.id, user.id)

    # Event with color restriction
    await set_event(db, session.id, game.id, "ColorPri", "1d6",
                    color_restriction="M", created_by=user.id)

    result = await handle_event_check(
        db, game.id, session.id, user.id, ghost, patient,
        "ColorPri", color="C",  # Player requests C, but event forces M
    )
    assert result.success is True
    assert result.data["color"] == "M"  # Event restriction wins
