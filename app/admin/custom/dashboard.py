"""Game state overview dashboard."""

from __future__ import annotations

from sqladmin import BaseView, expose
from starlette.requests import Request
from sqlalchemy import func, select

from app.infra.db import async_session_factory
from app.models.db_models import (
    ColorFragment,
    Game,
    Ghost,
    Location,
    Patient,
    Region,
    Session,
    TimelineEvent,
    User,
)


class DashboardView(BaseView):
    name = "Dashboard"
    icon = "fa-solid fa-chart-line"

    @expose("/dashboard", methods=["GET"])
    async def dashboard(self, request: Request):
        async with async_session_factory() as db:
            stats = {}
            for label, model in [
                ("users", User),
                ("games", Game),
                ("sessions", Session),
                ("patients", Patient),
                ("ghosts", Ghost),
                ("regions", Region),
                ("locations", Location),
                ("timeline_events", TimelineEvent),
                ("color_fragments", ColorFragment),
            ]:
                result = await db.execute(select(func.count(model.id)))
                stats[label] = result.scalar_one()

            # Active counts
            result = await db.execute(
                select(func.count(Game.id)).where(Game.status == "active")
            )
            stats["active_games"] = result.scalar_one()

            result = await db.execute(
                select(func.count(Session.id)).where(Session.status == "active")
            )
            stats["active_sessions"] = result.scalar_one()

            # Recent games
            result = await db.execute(
                select(Game).order_by(Game.created_at.desc()).limit(10)
            )
            recent_games = result.scalars().all()

            # Recent sessions
            result = await db.execute(
                select(Session).order_by(Session.started_at.desc()).limit(10)
            )
            recent_sessions = result.scalars().all()

        return await self.templates.TemplateResponse(
            request,
            "admin/dashboard.html",
            {"stats": stats, "recent_games": recent_games, "recent_sessions": recent_sessions},
        )
