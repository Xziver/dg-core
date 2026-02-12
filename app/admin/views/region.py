"""Admin views for Region and Location models."""

from sqladmin import ModelView

from app.models.db_models import Location, Region


class RegionAdmin(ModelView, model=Region):
    name = "Region"
    name_plural = "Regions"
    icon = "fa-solid fa-map"

    column_list = [
        Region.id,
        Region.code,
        Region.name,
        Region.game_id,
        Region.sort_order,
        Region.created_at,
    ]
    column_searchable_list = [Region.name, Region.code]
    column_sortable_list = [Region.code, Region.name, Region.sort_order]

    column_details_list = [
        Region.id,
        Region.code,
        Region.name,
        Region.description,
        Region.metadata_json,
        Region.game,
        Region.locations,
        Region.sort_order,
        Region.created_at,
    ]

    form_columns = [
        Region.game_id,
        Region.code,
        Region.name,
        Region.description,
        Region.metadata_json,
        Region.sort_order,
    ]

    can_export = True
    export_types = ["csv", "json"]


class LocationAdmin(ModelView, model=Location):
    name = "Location"
    name_plural = "Locations"
    icon = "fa-solid fa-location-dot"

    column_list = [
        Location.id,
        Location.name,
        Location.region_id,
        Location.sort_order,
        Location.created_at,
    ]
    column_searchable_list = [Location.name]
    column_sortable_list = [Location.name, Location.sort_order]

    column_details_list = [
        Location.id,
        Location.name,
        Location.description,
        Location.content,
        Location.metadata_json,
        Location.region,
        Location.sort_order,
        Location.created_at,
    ]

    form_columns = [
        Location.region_id,
        Location.name,
        Location.description,
        Location.content,
        Location.metadata_json,
        Location.sort_order,
    ]

    can_export = True
    export_types = ["csv", "json"]
