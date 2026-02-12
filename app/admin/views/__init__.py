"""Admin model view configurations."""

from app.admin.views.user import UserAdmin, PlatformBindingAdmin
from app.admin.views.game import (
    GameAdmin,
    GamePlayerAdmin,
    SessionAdmin,
    TimelineEventAdmin,
)
from app.admin.views.character import (
    PatientAdmin,
    GhostAdmin,
    PrintAbilityAdmin,
    ColorFragmentAdmin,
)
from app.admin.views.region import RegionAdmin, LocationAdmin

__all__ = [
    "UserAdmin",
    "PlatformBindingAdmin",
    "GameAdmin",
    "GamePlayerAdmin",
    "SessionAdmin",
    "TimelineEventAdmin",
    "PatientAdmin",
    "GhostAdmin",
    "PrintAbilityAdmin",
    "ColorFragmentAdmin",
    "RegionAdmin",
    "LocationAdmin",
]
