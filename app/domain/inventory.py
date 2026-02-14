"""Item and inventory management — define items, grant, use, list."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import buff as buff_mod, character
from app.models.db_models import Ghost, ItemDefinition, PlayerItem
from app.models.result import EngineResult, StateChange


async def create_item_definition(
    db: AsyncSession,
    game_id: str,
    name: str,
    description: str | None = None,
    item_type: str = "generic",
    effect: dict | None = None,
    stackable: bool = True,
) -> ItemDefinition:
    """Create an item definition (game-scoped)."""
    item_def = ItemDefinition(
        game_id=game_id,
        name=name,
        description=description,
        item_type=item_type,
        effect_json=json.dumps(effect) if effect else None,
        stackable=stackable,
    )
    db.add(item_def)
    await db.flush()
    return item_def


async def get_item_definition(
    db: AsyncSession, item_def_id: str
) -> ItemDefinition | None:
    result = await db.execute(
        select(ItemDefinition).where(ItemDefinition.id == item_def_id)
    )
    return result.scalar_one_or_none()


async def get_item_definitions(
    db: AsyncSession, game_id: str
) -> list[ItemDefinition]:
    result = await db.execute(
        select(ItemDefinition).where(ItemDefinition.game_id == game_id)
    )
    return list(result.scalars().all())


async def grant_item(
    db: AsyncSession,
    patient_id: str,
    item_def_id: str,
    count: int = 1,
) -> PlayerItem:
    """Grant item(s) to a patient. Stacks if stackable."""
    item_def = await get_item_definition(db, item_def_id)
    if item_def is None:
        raise ValueError(f"Item definition {item_def_id} not found")

    if item_def.stackable:
        existing_result = await db.execute(
            select(PlayerItem).where(
                PlayerItem.patient_id == patient_id,
                PlayerItem.item_def_id == item_def_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            existing.count += count
            await db.flush()
            return existing

    pi = PlayerItem(
        patient_id=patient_id,
        item_def_id=item_def_id,
        count=count,
    )
    db.add(pi)
    await db.flush()
    return pi


async def get_inventory(db: AsyncSession, patient_id: str) -> list[PlayerItem]:
    """Get all items in a patient's inventory."""
    result = await db.execute(
        select(PlayerItem).where(PlayerItem.patient_id == patient_id)
    )
    return list(result.scalars().all())


async def use_item(
    db: AsyncSession,
    game_id: str,
    patient_id: str,
    item_def_id: str,
    ghost: Ghost,
) -> EngineResult:
    """Use an item from inventory and apply its effect.

    Supported effect types:
    - heal_hp: {"type": "heal_hp", "value": N}
    - heal_mp: {"type": "heal_mp", "value": N}
    - apply_buff: {"type": "apply_buff", "buff_name": "...", "expression": "...", "duration": N}
    - cmyk_boost: {"type": "cmyk_boost", "color": "C", "value": N}
    """
    pi_result = await db.execute(
        select(PlayerItem).where(
            PlayerItem.patient_id == patient_id,
            PlayerItem.item_def_id == item_def_id,
        )
    )
    pi = pi_result.scalar_one_or_none()
    if pi is None:
        return EngineResult(
            success=False, event_type="item_use", error="Item not in inventory"
        )
    if pi.count <= 0:
        return EngineResult(
            success=False, event_type="item_use", error="No items remaining"
        )

    item_def = await get_item_definition(db, item_def_id)
    if item_def is None:
        return EngineResult(
            success=False, event_type="item_use", error="Item definition not found"
        )

    # Decrement count
    pi.count -= 1
    if pi.count <= 0:
        await db.delete(pi)

    # Apply effect
    state_changes: list[StateChange] = []
    effect_data: dict = {"item_name": item_def.name, "item_id": item_def.id}

    if item_def.effect_json:
        effect = json.loads(item_def.effect_json)
        effect_type = effect.get("type")

        if effect_type == "heal_hp":
            value = effect.get("value", 1)
            old_hp = ghost.hp
            new_hp = min(ghost.hp + value, ghost.hp_max)
            ghost.hp = new_hp
            effect_data["heal_hp"] = new_hp - old_hp
            state_changes.append(
                StateChange(
                    entity_type="ghost",
                    entity_id=ghost.id,
                    field="hp",
                    old_value=str(old_hp),
                    new_value=str(new_hp),
                )
            )

        elif effect_type == "heal_mp":
            value = effect.get("value", 1)
            old_mp = ghost.mp
            new_mp = min(ghost.mp + value, ghost.mp_max)
            ghost.mp = new_mp
            effect_data["heal_mp"] = new_mp - old_mp
            state_changes.append(
                StateChange(
                    entity_type="ghost",
                    entity_id=ghost.id,
                    field="mp",
                    old_value=str(old_mp),
                    new_value=str(new_mp),
                )
            )

        elif effect_type == "apply_buff":
            buff = await buff_mod.add_buff(
                db,
                ghost.id,
                game_id,
                name=effect.get("buff_name", item_def.name),
                expression=effect.get("expression", "+1"),
                remaining_rounds=effect.get("duration", 1),
            )
            effect_data["buff_applied"] = buff.name

        elif effect_type == "cmyk_boost":
            color = effect.get("color", "C")
            value = effect.get("value", 1)
            await character.apply_color_fragment(db, ghost, color, value)
            effect_data["cmyk_boost"] = {"color": color, "value": value}

    await db.flush()

    return EngineResult(
        success=True,
        event_type="item_use",
        data=effect_data,
        state_changes=state_changes,
    )
