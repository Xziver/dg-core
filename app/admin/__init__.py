"""Admin dashboard — setup and configuration for sqladmin."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin

from app.admin.auth import AdminAuth
from app.admin.views import (
    ColorFragmentAdmin,
    GameAdmin,
    GamePlayerAdmin,
    GhostAdmin,
    LocationAdmin,
    PatientAdmin,
    PlatformBindingAdmin,
    PrintAbilityAdmin,
    RegionAdmin,
    SessionAdmin,
    TimelineEventAdmin,
    UserAdmin,
)
from app.infra.config import settings
from app.infra.db import engine

TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates")


def setup_admin(app: FastAPI) -> Admin:
    """Configure and mount the sqladmin dashboard on the FastAPI app."""
    authentication_backend = AdminAuth(secret_key=settings.jwt_secret_key)

    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=authentication_backend,
        base_url="/admin",
        title="DG-Core Admin",
        templates_dir=TEMPLATES_DIR,
    )

    # Model views
    admin.add_view(UserAdmin)
    admin.add_view(PlatformBindingAdmin)
    admin.add_view(GameAdmin)
    admin.add_view(GamePlayerAdmin)
    admin.add_view(RegionAdmin)
    admin.add_view(LocationAdmin)
    admin.add_view(PatientAdmin)
    admin.add_view(GhostAdmin)
    admin.add_view(PrintAbilityAdmin)
    admin.add_view(SessionAdmin)
    admin.add_view(TimelineEventAdmin)
    admin.add_view(ColorFragmentAdmin)

    # Custom views
    from app.admin.custom.dashboard import DashboardView
    from app.admin.custom.cmyk_editor import CMYKEditorView
    from app.admin.custom.bulk_ops import BulkOpsView

    admin.add_view(DashboardView)
    admin.add_view(CMYKEditorView)
    admin.add_view(BulkOpsView)

    return admin
