"""Visual CMYK editor for Ghost attributes."""

from __future__ import annotations

import json

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import select

from app.infra.db import async_session_factory
from app.models.db_models import Game, Ghost


class CMYKEditorView(BaseView):
    name = "CMYK Editor"
    icon = "fa-solid fa-palette"

    @expose("/cmyk-editor", methods=["GET"])
    async def editor_page(self, request: Request):
        game_id = request.query_params.get("game_id", "")
        ghosts = []
        games = []

        async with async_session_factory() as db:
            # Always load game list for the selector
            result = await db.execute(
                select(Game).order_by(Game.created_at.desc())
            )
            games = [{"id": g.id, "name": g.name} for g in result.scalars().all()]

            if game_id:
                result = await db.execute(
                    select(Ghost).where(Ghost.game_id == game_id)
                )
                raw_ghosts = result.scalars().all()
                for g in raw_ghosts:
                    try:
                        raw_cmyk = json.loads(g.cmyk_json)
                        cmyk = {
                            "C": int(raw_cmyk.get("C", 0)),
                            "M": int(raw_cmyk.get("M", 0)),
                            "Y": int(raw_cmyk.get("Y", 0)),
                            "K": int(raw_cmyk.get("K", 0)),
                        }
                    except (json.JSONDecodeError, TypeError, ValueError):
                        cmyk = {"C": 0, "M": 0, "Y": 0, "K": 0}
                    ghosts.append({
                        "id": g.id,
                        "name": g.name,
                        "cmyk": cmyk,
                        "hp": g.hp,
                        "hp_max": g.hp_max,
                    })

        return await self.templates.TemplateResponse(
            request,
            "admin/cmyk_editor.html",
            {"ghosts": ghosts, "games": games, "game_id": game_id},
        )

    @expose("/cmyk-editor/save", methods=["POST"])
    async def save_cmyk(self, request: Request):
        form = await request.form()
        ghost_id = form.get("ghost_id", "")
        game_id = form.get("game_id", "")

        try:
            c = max(0, int(form.get("C", 0)))
            m = max(0, int(form.get("M", 0)))
            y = max(0, int(form.get("Y", 0)))
            k = max(0, int(form.get("K", 0)))
        except (ValueError, TypeError):
            return RedirectResponse(
                url=f"/admin/cmyk-editor?game_id={game_id}", status_code=303
            )

        async with async_session_factory() as db:
            result = await db.execute(select(Ghost).where(Ghost.id == ghost_id))
            ghost = result.scalar_one_or_none()
            if ghost:
                ghost.cmyk_json = json.dumps({"C": c, "M": m, "Y": y, "K": k})
                await db.commit()

        return RedirectResponse(
            url=f"/admin/cmyk-editor?game_id={game_id}", status_code=303
        )
