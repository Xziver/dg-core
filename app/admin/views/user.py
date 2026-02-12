"""Admin views for User and PlatformBinding models."""

from sqladmin import ModelView

from app.models.db_models import PlatformBinding, User


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"

    column_list = [User.id, User.username, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.username, User.id]
    column_sortable_list = [User.username, User.created_at, User.role]
    column_default_sort = ("created_at", True)

    form_columns = ["username", "email", "role", "is_active"]

    column_details_list = [
        User.id,
        User.username,
        User.email,
        User.role,
        User.is_active,
        User.created_at,
        User.platform_bindings,
        User.game_links,
        User.patients,
    ]

    can_export = True
    export_types = ["csv", "json"]


class PlatformBindingAdmin(ModelView, model=PlatformBinding):
    name = "Platform Binding"
    name_plural = "Platform Bindings"
    icon = "fa-solid fa-link"

    column_list = [
        PlatformBinding.id,
        PlatformBinding.platform,
        PlatformBinding.platform_uid,
        PlatformBinding.user,
        PlatformBinding.bound_at,
    ]
    column_searchable_list = [PlatformBinding.platform, PlatformBinding.platform_uid]
    column_sortable_list = [PlatformBinding.platform, PlatformBinding.bound_at]

    form_columns = [
        "user",
        "platform",
        "platform_uid",
    ]

    can_export = True
    export_types = ["csv"]
