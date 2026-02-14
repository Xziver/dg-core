"""Bulk import/export operations."""

from __future__ import annotations

import csv
import io

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import StreamingResponse
from sqlalchemy import select

from app.infra.db import async_session_factory
from app.models.db_models import Ghost, Location, Patient, Region


class BulkOpsView(BaseView):
    name = "Bulk Operations"
    icon = "fa-solid fa-file-import"

    @expose("/bulk", methods=["GET"])
    async def bulk_page(self, request: Request):
        return await self.templates.TemplateResponse(request, "admin/bulk_import.html", {})

    # --- Region import/export ---

    @expose("/bulk/import-regions", methods=["POST"])
    async def import_regions(self, request: Request):
        return await self._import_entity(request, "Region", _create_region)

    @expose("/bulk/export-regions", methods=["GET"])
    async def export_regions(self, request: Request):
        async with async_session_factory() as db:
            result = await db.execute(select(Region))
            rows = result.scalars().all()
        return _csv_response(
            "regions.csv",
            ["id", "game_id", "code", "name", "description", "sort_order"],
            [[r.id, r.game_id, r.code, r.name, r.description or "", r.sort_order] for r in rows],
        )

    # --- Location import/export ---

    @expose("/bulk/import-locations", methods=["POST"])
    async def import_locations(self, request: Request):
        return await self._import_entity(request, "Location", _create_location)

    @expose("/bulk/export-locations", methods=["GET"])
    async def export_locations(self, request: Request):
        async with async_session_factory() as db:
            result = await db.execute(select(Location))
            rows = result.scalars().all()
        return _csv_response(
            "locations.csv",
            ["id", "region_id", "name", "description", "content", "sort_order"],
            [
                [r.id, r.region_id, r.name, r.description or "", r.content or "", r.sort_order]
                for r in rows
            ],
        )

    # --- Patient import/export ---

    @expose("/bulk/import-patients", methods=["POST"])
    async def import_patients(self, request: Request):
        return await self._import_entity(request, "Patient", _create_patient)

    @expose("/bulk/export-patients", methods=["GET"])
    async def export_patients(self, request: Request):
        async with async_session_factory() as db:
            result = await db.execute(select(Patient))
            rows = result.scalars().all()
        return _csv_response(
            "patients.csv",
            ["id", "user_id", "game_id", "name", "soul_color", "gender", "age", "identity"],
            [
                [r.id, r.user_id, r.game_id, r.name, r.soul_color, r.gender or "", r.age or "", r.identity or ""]
                for r in rows
            ],
        )

    # --- Ghost import/export ---

    @expose("/bulk/import-ghosts", methods=["POST"])
    async def import_ghosts(self, request: Request):
        return await self._import_entity(request, "Ghost", _create_ghost)

    @expose("/bulk/export-ghosts", methods=["GET"])
    async def export_ghosts(self, request: Request):
        async with async_session_factory() as db:
            result = await db.execute(select(Ghost))
            rows = result.scalars().all()
        return _csv_response(
            "ghosts.csv",
            ["id", "current_patient_id", "origin_patient_id", "creator_user_id", "game_id", "name", "cmyk_json", "hp", "hp_max"],
            [
                [r.id, r.current_patient_id or "", r.origin_patient_id or "", r.creator_user_id, r.game_id, r.name, r.cmyk_json, r.hp, r.hp_max]
                for r in rows
            ],
        )

    # --- Generic import helper ---

    async def _import_entity(self, request: Request, entity_name: str, factory):
        form = await request.form()
        upload = form.get("file")
        if not upload:
            return await self.templates.TemplateResponse(
                request,
                "admin/bulk_result.html",
                {"success": False, "error": "No file uploaded", "entity": entity_name},
            )

        content = (await upload.read()).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        created = 0
        errors = []

        async with async_session_factory() as db:
            for i, row in enumerate(reader, start=2):
                try:
                    obj = factory(row)
                    db.add(obj)
                    created += 1
                except Exception as e:
                    errors.append(f"Row {i}: {e}")
            if created > 0:
                await db.commit()

        return await self.templates.TemplateResponse(
            request,
            "admin/bulk_result.html",
            {"success": True, "created": created, "errors": errors, "entity": entity_name},
        )


# --- Factory functions for creating model instances from CSV rows ---


def _create_region(row: dict) -> Region:
    return Region(
        game_id=row["game_id"],
        code=row["code"],
        name=row["name"],
        description=row.get("description") or None,
        sort_order=int(row.get("sort_order", 0)),
    )


def _create_location(row: dict) -> Location:
    return Location(
        region_id=row["region_id"],
        name=row["name"],
        description=row.get("description") or None,
        content=row.get("content") or None,
        sort_order=int(row.get("sort_order", 0)),
    )


def _create_patient(row: dict) -> Patient:
    return Patient(
        user_id=row["user_id"],
        game_id=row["game_id"],
        name=row["name"],
        soul_color=row["soul_color"],
        gender=row.get("gender") or None,
        age=int(row["age"]) if row.get("age") else None,
        identity=row.get("identity") or None,
    )


def _create_ghost(row: dict) -> Ghost:
    import json

    cmyk = row.get("cmyk_json", '{"C":0,"M":0,"Y":0,"K":0}')
    # Validate JSON
    json.loads(cmyk)
    return Ghost(
        current_patient_id=row.get("current_patient_id") or None,
        origin_patient_id=row.get("origin_patient_id") or None,
        creator_user_id=row["creator_user_id"],
        game_id=row["game_id"],
        name=row["name"],
        cmyk_json=cmyk,
        hp=int(row.get("hp", 10)),
        hp_max=int(row.get("hp_max", 10)),
    )


def _csv_response(filename: str, headers: list[str], rows: list[list]) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
