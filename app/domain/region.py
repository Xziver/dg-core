"""Region and location management — CRUD + player movement."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import GamePlayer, Location, Region


# --- Region ---

async def create_region(
    db: AsyncSession,
    game_id: str,
    name: str,
    code: str,
    description: str | None = None,
    metadata: dict | None = None,
    sort_order: int = 0,
) -> Region:
    region = Region(
        game_id=game_id,
        code=code.upper(),
        name=name,
        description=description,
        metadata_json=json.dumps(metadata) if metadata else None,
        sort_order=sort_order,
    )
    db.add(region)
    await db.flush()
    return region


async def get_region(db: AsyncSession, region_id: str) -> Region | None:
    result = await db.execute(select(Region).where(Region.id == region_id))
    return result.scalar_one_or_none()


async def get_regions(db: AsyncSession, game_id: str) -> list[Region]:
    result = await db.execute(
        select(Region)
        .where(Region.game_id == game_id)
        .order_by(Region.sort_order)
    )
    return list(result.scalars().all())


# --- Location ---

async def create_location(
    db: AsyncSession,
    region_id: str,
    name: str,
    description: str | None = None,
    content: str | None = None,
    metadata: dict | None = None,
    sort_order: int = 0,
) -> Location:
    location = Location(
        region_id=region_id,
        name=name,
        description=description,
        content=content,
        metadata_json=json.dumps(metadata) if metadata else None,
        sort_order=sort_order,
    )
    db.add(location)
    await db.flush()
    return location


async def get_location(db: AsyncSession, location_id: str) -> Location | None:
    result = await db.execute(select(Location).where(Location.id == location_id))
    return result.scalar_one_or_none()


async def get_locations(db: AsyncSession, region_id: str) -> list[Location]:
    result = await db.execute(
        select(Location)
        .where(Location.region_id == region_id)
        .order_by(Location.sort_order)
    )
    return list(result.scalars().all())


# --- Player movement ---

async def move_player(
    db: AsyncSession,
    game_id: str,
    user_id: str,
    region_id: str | None = None,
    location_id: str | None = None,
) -> GamePlayer:
    """Update a player's current region and/or location."""
    result = await db.execute(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    )
    gp = result.scalar_one_or_none()
    if gp is None:
        raise ValueError(f"Player {user_id} not found in game {game_id}")
    if region_id is not None:
        gp.current_region_id = region_id
    if location_id is not None:
        gp.current_location_id = location_id
    await db.flush()
    return gp
