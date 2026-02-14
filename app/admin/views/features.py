"""Admin views for new game feature models."""

from sqladmin import ModelView

from app.models.db_models import (
    Buff,
    CommunicationRequest,
    EventAbilityUsage,
    EventDefinition,
    ItemDefinition,
    PlayerItem,
    SessionPlayer,
)


class SessionPlayerAdmin(ModelView, model=SessionPlayer):
    name = "Session Player"
    name_plural = "Session Players"
    icon = "fa-solid fa-people-group"

    column_list = [
        SessionPlayer.id,
        "session",
        "patient",
        SessionPlayer.joined_at,
    ]
    column_searchable_list = [SessionPlayer.session_id, SessionPlayer.patient_id]
    column_sortable_list = [SessionPlayer.joined_at]
    column_default_sort = ("joined_at", True)

    form_columns = ["session", "patient"]


class BuffAdmin(ModelView, model=Buff):
    name = "Buff"
    name_plural = "Buffs"
    icon = "fa-solid fa-shield-halved"

    column_list = [
        Buff.id,
        Buff.name,
        Buff.expression,
        Buff.buff_type,
        Buff.remaining_rounds,
        "ghost",
        "game",
    ]
    column_searchable_list = [Buff.name, Buff.ghost_id]
    column_sortable_list = [Buff.name, Buff.buff_type, Buff.remaining_rounds, Buff.created_at]
    column_default_sort = ("created_at", True)

    form_columns = [
        "ghost",
        "game",
        "name",
        "expression",
        "buff_type",
        "remaining_rounds",
        "created_by",
    ]


class EventDefinitionAdmin(ModelView, model=EventDefinition):
    name = "Event Definition"
    name_plural = "Event Definitions"
    icon = "fa-solid fa-bullseye"

    column_list = [
        EventDefinition.id,
        EventDefinition.name,
        EventDefinition.expression,
        EventDefinition.color_restriction,
        EventDefinition.is_active,
        EventDefinition.target_roll_total,
        "session",
    ]
    column_searchable_list = [EventDefinition.name, EventDefinition.session_id]
    column_sortable_list = [EventDefinition.name, EventDefinition.is_active, EventDefinition.created_at]
    column_default_sort = ("created_at", True)

    form_columns = [
        "session",
        "game",
        "name",
        "expression",
        "color_restriction",
        "is_active",
        "created_by",
    ]


class EventAbilityUsageAdmin(ModelView, model=EventAbilityUsage):
    name = "Event Ability Usage"
    name_plural = "Event Ability Usages"
    icon = "fa-solid fa-check-double"

    column_list = [
        EventAbilityUsage.id,
        EventAbilityUsage.event_def_id,
        EventAbilityUsage.ghost_id,
        EventAbilityUsage.ability_id,
        EventAbilityUsage.used_at,
    ]
    column_searchable_list = [EventAbilityUsage.event_def_id, EventAbilityUsage.ghost_id]
    column_sortable_list = [EventAbilityUsage.used_at]

    form_columns = [
        "event_def_id",
        "ghost_id",
        "ability_id",
    ]


class CommunicationRequestAdmin(ModelView, model=CommunicationRequest):
    name = "Communication Request"
    name_plural = "Communication Requests"
    icon = "fa-solid fa-comments"

    column_list = [
        CommunicationRequest.id,
        CommunicationRequest.status,
        "initiator_patient",
        "target_patient",
        "game",
        CommunicationRequest.created_at,
        CommunicationRequest.resolved_at,
    ]
    column_searchable_list = [CommunicationRequest.game_id, CommunicationRequest.status]
    column_sortable_list = [CommunicationRequest.status, CommunicationRequest.created_at]
    column_default_sort = ("created_at", True)

    form_columns = [
        "game",
        "initiator_patient",
        "target_patient",
        "status",
        "transferred_ability_id",
    ]


class ItemDefinitionAdmin(ModelView, model=ItemDefinition):
    name = "Item Definition"
    name_plural = "Item Definitions"
    icon = "fa-solid fa-scroll"

    column_list = [
        ItemDefinition.id,
        ItemDefinition.name,
        ItemDefinition.item_type,
        ItemDefinition.stackable,
        "game",
    ]
    column_searchable_list = [ItemDefinition.name, ItemDefinition.game_id]
    column_sortable_list = [ItemDefinition.name, ItemDefinition.item_type, ItemDefinition.created_at]
    column_default_sort = ("created_at", True)

    form_columns = [
        "game",
        "name",
        "description",
        "item_type",
        "effect_json",
        "stackable",
    ]


class PlayerItemAdmin(ModelView, model=PlayerItem):
    name = "Player Item"
    name_plural = "Player Items"
    icon = "fa-solid fa-box"

    column_list = [
        PlayerItem.id,
        "patient",
        "item_definition",
        PlayerItem.count,
        PlayerItem.acquired_at,
    ]
    column_searchable_list = [PlayerItem.patient_id, PlayerItem.item_def_id]
    column_sortable_list = [PlayerItem.count, PlayerItem.acquired_at]
    column_default_sort = ("acquired_at", True)

    form_columns = [
        "patient",
        "item_definition",
        "count",
    ]
