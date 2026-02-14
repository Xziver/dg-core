"""Communication system — cross-player information sharing and ability transfer."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import character
from app.models.db_models import CommunicationRequest, Ghost, Patient


async def request_communication(
    db: AsyncSession,
    game_id: str,
    initiator_patient_id: str,
    target_patient_id: str,
) -> CommunicationRequest:
    """Initiate a communication request. Costs 1 MP.

    Validates:
    - Initiator has MP >= 1
    - Initiator has > 0 value in target's soul_color
    - No duplicate pending request
    """
    # Get initiator's ghost
    initiator_ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == initiator_patient_id)
    )
    initiator_ghost = initiator_ghost_result.scalar_one_or_none()
    if initiator_ghost is None:
        raise ValueError("Initiator has no companion ghost")

    if initiator_ghost.mp < 1:
        raise ValueError("Not enough MP to initiate communication (requires 1 MP)")

    # Get target patient's soul_color
    target_patient = await character.get_patient(db, target_patient_id)
    if target_patient is None:
        raise ValueError("Target patient not found")

    # Check initiator has value in target's soul_color
    target_color = target_patient.soul_color.upper()
    color_value = character.get_color_value(initiator_ghost, target_color)
    if color_value <= 0:
        raise ValueError(
            f"Cannot communicate: your {target_color} value is 0 "
            f"(target's soul color is {target_color})"
        )

    # Check no duplicate pending request
    existing = await db.execute(
        select(CommunicationRequest).where(
            CommunicationRequest.initiator_patient_id == initiator_patient_id,
            CommunicationRequest.target_patient_id == target_patient_id,
            CommunicationRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("A pending communication request already exists")

    # Deduct MP
    initiator_ghost.mp -= 1

    comm = CommunicationRequest(
        game_id=game_id,
        initiator_patient_id=initiator_patient_id,
        target_patient_id=target_patient_id,
    )
    db.add(comm)
    await db.flush()
    return comm


async def accept_communication(
    db: AsyncSession,
    request_id: str,
    ability_id: str | None = None,
) -> dict:
    """Accept a communication request.

    Shares Patient+Ghost info and transfers one PrintAbility from target to initiator.
    """
    comm = await _get_request(db, request_id, expected_status="pending")

    # Get target ghost to find abilities
    target_ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == comm.target_patient_id)
    )
    target_ghost = target_ghost_result.scalar_one_or_none()
    if target_ghost is None:
        raise ValueError("Target has no companion ghost")

    # Get target's abilities
    abilities = await character.get_print_abilities(db, target_ghost.id)

    # Determine which ability to transfer
    ability_to_transfer = None
    if abilities:
        if len(abilities) == 1:
            ability_to_transfer = abilities[0]
        elif ability_id:
            ability_to_transfer = next(
                (a for a in abilities if a.id == ability_id), None
            )
            if ability_to_transfer is None:
                raise ValueError(f"Ability {ability_id} not found on target ghost")
        else:
            raise ValueError(
                "Target has multiple abilities, must specify ability_id. "
                f"Available: {[{'id': a.id, 'name': a.name, 'color': a.color} for a in abilities]}"
            )

    # Get initiator ghost
    initiator_ghost_result = await db.execute(
        select(Ghost).where(Ghost.current_patient_id == comm.initiator_patient_id)
    )
    initiator_ghost = initiator_ghost_result.scalar_one_or_none()
    if initiator_ghost is None:
        raise ValueError("Initiator has no companion ghost")

    # Transfer: create a copy of the ability on initiator's ghost
    new_ability = None
    if ability_to_transfer is not None:
        new_ability = await character.add_print_ability(
            db,
            ghost_id=initiator_ghost.id,
            name=ability_to_transfer.name,
            color=ability_to_transfer.color,
            description=ability_to_transfer.description,
            ability_count=ability_to_transfer.ability_count,
        )
        comm.transferred_ability_id = new_ability.id

    # Mark request as accepted
    comm.status = "accepted"
    comm.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    # Build shared info
    initiator_patient = await character.get_patient(db, comm.initiator_patient_id)
    target_patient = await character.get_patient(db, comm.target_patient_id)

    result: dict = {
        "request_id": comm.id,
        "status": "accepted",
        "initiator_info": _patient_ghost_summary(initiator_patient, initiator_ghost),
        "target_info": _patient_ghost_summary(target_patient, target_ghost),
    }
    if new_ability is not None:
        result["transferred_ability"] = {
            "id": new_ability.id,
            "name": new_ability.name,
            "color": new_ability.color,
        }
    return result


async def reject_communication(
    db: AsyncSession, request_id: str
) -> CommunicationRequest:
    """Reject a pending communication request."""
    comm = await _get_request(db, request_id, expected_status="pending")
    comm.status = "rejected"
    comm.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return comm


async def cancel_communication(
    db: AsyncSession, request_id: str
) -> CommunicationRequest:
    """Cancel a pending communication request."""
    comm = await _get_request(db, request_id, expected_status="pending")
    comm.status = "cancelled"
    comm.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return comm


async def get_pending_requests(
    db: AsyncSession, game_id: str, patient_id: str
) -> list[CommunicationRequest]:
    """Get pending requests targeting a specific patient."""
    result = await db.execute(
        select(CommunicationRequest).where(
            CommunicationRequest.game_id == game_id,
            CommunicationRequest.target_patient_id == patient_id,
            CommunicationRequest.status == "pending",
        )
    )
    return list(result.scalars().all())


async def _get_request(
    db: AsyncSession, request_id: str, expected_status: str | None = None
) -> CommunicationRequest:
    result = await db.execute(
        select(CommunicationRequest).where(CommunicationRequest.id == request_id)
    )
    comm = result.scalar_one_or_none()
    if comm is None:
        raise ValueError(f"Communication request {request_id} not found")
    if expected_status and comm.status != expected_status:
        raise ValueError(f"Request is {comm.status}, expected {expected_status}")
    return comm


def _patient_ghost_summary(patient: Patient | None, ghost: Ghost | None) -> dict:
    """Build a summary dict for communication info sharing."""
    result: dict = {}
    if patient:
        result["patient"] = {
            "id": patient.id,
            "name": patient.name,
            "soul_color": patient.soul_color,
            "gender": patient.gender,
            "age": patient.age,
            "identity": patient.identity,
            "region_id": patient.current_region_id,
            "location_id": patient.current_location_id,
        }
    if ghost:
        result["ghost"] = {
            "id": ghost.id,
            "name": ghost.name,
            "cmyk": json.loads(ghost.cmyk_json),
            "hp": ghost.hp,
            "hp_max": ghost.hp_max,
            "mp": ghost.mp,
            "mp_max": ghost.mp_max,
        }
    return result
