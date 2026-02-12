"""Promote a user to admin role.

Usage:
    python scripts/promote_admin.py <user_id>
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, update

from app.infra.db import async_session_factory, init_db
from app.models.db_models import User


async def promote(user_id: str) -> None:
    await init_db()
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"Error: User '{user_id}' not found.")
            sys.exit(1)

        if user.role == "admin":
            print(f"User '{user.username}' (id={user_id}) is already an admin.")
            return

        await db.execute(update(User).where(User.id == user_id).values(role="admin"))
        await db.commit()
        print(f"User '{user.username}' (id={user_id}) promoted to admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/promote_admin.py <user_id>")
        sys.exit(1)
    asyncio.run(promote(sys.argv[1]))
