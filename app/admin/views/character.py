"""Admin views for Patient, Ghost, PrintAbility, and ColorFragment models."""

from __future__ import annotations

import json

from sqladmin import ModelView

from app.models.db_models import ColorFragment, Ghost, Patient, PrintAbility


def _format_cmyk(model: Ghost, name: str) -> str:
    """Format CMYK JSON as readable text for list view."""
    try:
        cmyk = json.loads(model.cmyk_json)
        return f"C:{cmyk.get('C', 0)} M:{cmyk.get('M', 0)} Y:{cmyk.get('Y', 0)} K:{cmyk.get('K', 0)}"
    except (json.JSONDecodeError, TypeError):
        return str(model.cmyk_json)


class PatientAdmin(ModelView, model=Patient):
    name = "Patient"
    name_plural = "Patients"
    icon = "fa-solid fa-person"

    column_list = [
        Patient.id,
        Patient.name,
        Patient.soul_color,
        "user",
        "game",
        Patient.created_at,
    ]
    column_searchable_list = [Patient.name, Patient.id]
    column_sortable_list = [Patient.name, Patient.soul_color, Patient.created_at]

    column_details_list = [
        Patient.id,
        Patient.name,
        Patient.soul_color,
        Patient.gender,
        Patient.age,
        Patient.identity,
        Patient.portrait_url,
        Patient.personality_archives_json,
        Patient.ideal_projection,
        Patient.user,
        Patient.game,
        Patient.ghost,
        Patient.origin_ghost,
        Patient.created_at,
    ]

    form_columns = [
        "user",
        "game",
        "name",
        "soul_color",
        "gender",
        "age",
        "identity",
        "portrait_url",
        "personality_archives_json",
        "ideal_projection",
    ]

    can_export = True
    export_types = ["csv", "json"]


class GhostAdmin(ModelView, model=Ghost):
    name = "Ghost"
    name_plural = "Ghosts"
    icon = "fa-solid fa-ghost"

    column_list = [
        Ghost.id,
        Ghost.name,
        "current_patient",
        "origin_patient",
        Ghost.cmyk_json,
        Ghost.hp,
        Ghost.hp_max,
        "game",
    ]
    column_searchable_list = [Ghost.name, Ghost.id]
    column_sortable_list = [Ghost.name, Ghost.hp, Ghost.created_at]

    column_formatters = {
        Ghost.cmyk_json: _format_cmyk,
    }

    column_details_list = [
        Ghost.id,
        Ghost.name,
        Ghost.current_patient,
        Ghost.origin_patient,
        Ghost.game,
        "creator_user",
        Ghost.cmyk_json,
        Ghost.hp,
        Ghost.hp_max,
        Ghost.appearance,
        Ghost.personality,
        Ghost.origin_name,
        Ghost.origin_identity,
        Ghost.origin_soul_color,
        Ghost.origin_ideal_projection,
        Ghost.origin_archives_json,
        Ghost.archive_unlock_json,
        Ghost.origin_name_unlocked,
        Ghost.origin_identity_unlocked,
        Ghost.print_abilities,
        Ghost.color_fragments,
        Ghost.created_at,
    ]

    form_columns = [
        "current_patient",
        "origin_patient",
        "creator_user",
        "game",
        "name",
        "appearance",
        "personality",
        "cmyk_json",
        "hp",
        "hp_max",
        "origin_name",
        "origin_identity",
        "origin_soul_color",
        "origin_ideal_projection",
        "origin_archives_json",
        "archive_unlock_json",
        "origin_name_unlocked",
        "origin_identity_unlocked",
    ]

    can_export = True
    export_types = ["csv", "json"]


class PrintAbilityAdmin(ModelView, model=PrintAbility):
    name = "Print Ability"
    name_plural = "Print Abilities"
    icon = "fa-solid fa-wand-magic-sparkles"

    column_list = [
        PrintAbility.id,
        PrintAbility.name,
        PrintAbility.color,
        PrintAbility.ability_count,
        "ghost",
    ]
    column_searchable_list = [PrintAbility.name]
    column_sortable_list = [PrintAbility.name, PrintAbility.color]

    form_columns = [
        "ghost",
        "name",
        "description",
        "color",
        "ability_count",
    ]


class ColorFragmentAdmin(ModelView, model=ColorFragment):
    name = "Color Fragment"
    name_plural = "Color Fragments"
    icon = "fa-solid fa-puzzle-piece"

    column_list = [
        ColorFragment.id,
        ColorFragment.color,
        ColorFragment.value,
        ColorFragment.redeemed,
        "holder_ghost",
        "game",
    ]
    column_sortable_list = [ColorFragment.color, ColorFragment.value, ColorFragment.redeemed]

    form_columns = [
        "game",
        "holder_ghost",
        "color",
        "value",
        "redeemed",
    ]
