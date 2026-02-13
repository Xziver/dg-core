"""Admin views for Game, GamePlayer, Session, and TimelineEvent models."""

from sqladmin import ModelView

from app.models.db_models import Game, GamePlayer, Session, TimelineEvent


class GameAdmin(ModelView, model=Game):
    name = "Game"
    name_plural = "Games"
    icon = "fa-solid fa-gamepad"

    column_list = [Game.id, Game.name, Game.status, "creator", Game.created_at]
    column_searchable_list = [Game.name, Game.id]
    column_sortable_list = [Game.name, Game.status, Game.created_at]
    column_default_sort = ("created_at", True)

    column_details_list = [
        Game.id,
        Game.name,
        Game.status,
        Game.config_json,
        Game.flags_json,
        "creator",
        Game.created_at,
        Game.user_links,
        Game.regions,
        Game.patients,
        Game.ghosts,
        Game.sessions,
    ]

    form_columns = ["name", "status", "config_json", "flags_json", "creator"]

    can_export = True
    export_types = ["csv", "json"]


class GamePlayerAdmin(ModelView, model=GamePlayer):
    name = "Game Player"
    name_plural = "Game Players"
    icon = "fa-solid fa-user-group"

    column_list = [
        "game",
        "user",
        GamePlayer.role,
        "active_patient",
        "current_region",
        "current_location",
        GamePlayer.joined_at,
    ]
    column_searchable_list = [GamePlayer.game_id, GamePlayer.user_id]
    column_sortable_list = [GamePlayer.role, GamePlayer.joined_at]

    form_columns = [
        "game",
        "user",
        "role",
        "active_patient",
        "current_region",
        "current_location",
    ]


class SessionAdmin(ModelView, model=Session):
    name = "Session"
    name_plural = "Sessions"
    icon = "fa-solid fa-clock"

    column_list = [
        Session.id,
        "game",
        Session.status,
        "started_by_user",
        Session.started_at,
        Session.ended_at,
    ]
    column_searchable_list = [Session.id, Session.game_id]
    column_sortable_list = [Session.status, Session.started_at]
    column_default_sort = ("started_at", True)

    column_details_list = [
        Session.id,
        "game",
        "region",
        Session.status,
        "started_by_user",
        Session.started_at,
        Session.ended_at,
        Session.timeline_events,
    ]

    form_columns = [
        "game",
        "region",
        "started_by_user",
        "status",
    ]

    can_export = True


class TimelineEventAdmin(ModelView, model=TimelineEvent):
    name = "Timeline Event"
    name_plural = "Timeline Events"
    icon = "fa-solid fa-timeline"

    column_list = [
        TimelineEvent.id,
        "session",
        TimelineEvent.seq,
        TimelineEvent.event_type,
        TimelineEvent.actor_id,
        TimelineEvent.created_at,
    ]
    column_searchable_list = [TimelineEvent.event_type, TimelineEvent.session_id]
    column_sortable_list = [TimelineEvent.seq, TimelineEvent.created_at]
    column_default_sort = ("created_at", True)

    column_details_list = [
        TimelineEvent.id,
        "session",
        "game",
        TimelineEvent.seq,
        TimelineEvent.event_type,
        TimelineEvent.actor_id,
        TimelineEvent.data_json,
        TimelineEvent.result_json,
        TimelineEvent.narrative,
        TimelineEvent.created_at,
    ]

    form_columns = [
        "session",
        "game",
        "seq",
        "event_type",
        "actor_id",
        "data_json",
        "result_json",
        "narrative",
    ]

    can_export = True
    export_max_rows = 10000
