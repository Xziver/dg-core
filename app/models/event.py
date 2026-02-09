"""Game event schemas — input to the engine dispatcher."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # System events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"

    # Action events
    SKILL_CHECK = "skill_check"
    EXPLORE = "explore"

    # Combat events
    ATTACK = "attack"
    DEFEND = "defend"
    USE_PRINT_ABILITY = "use_print_ability"

    # Communication events
    INITIATE_COMM = "initiate_comm"
    DOWNLOAD_ABILITY = "download_ability"
    DEEP_SCAN = "deep_scan"
    ATTEMPT_SEIZE = "attempt_seize"

    # State events
    APPLY_FRAGMENT = "apply_fragment"
    HP_CHANGE = "hp_change"
    SECTOR_TRANSITION = "sector_transition"


# --- Payload models ---

class SessionStartPayload(BaseModel):
    event_type: Literal["session_start"] = "session_start"


class SessionEndPayload(BaseModel):
    event_type: Literal["session_end"] = "session_end"


class PlayerJoinPayload(BaseModel):
    event_type: Literal["player_join"] = "player_join"
    role: str = "PL"  # "KP" or "PL"


class PlayerLeavePayload(BaseModel):
    event_type: Literal["player_leave"] = "player_leave"


class SkillCheckPayload(BaseModel):
    event_type: Literal["skill_check"] = "skill_check"
    color: str  # C/M/Y/K
    difficulty: int
    context: str = ""


class ExplorePayload(BaseModel):
    event_type: Literal["explore"] = "explore"
    target_area: str


class AttackPayload(BaseModel):
    event_type: Literal["attack"] = "attack"
    attacker_ghost_id: str
    target_ghost_id: str
    color_used: str  # C/M/Y/K


class DefendPayload(BaseModel):
    event_type: Literal["defend"] = "defend"
    defender_ghost_id: str
    color_used: str  # C/M/Y/K


class UsePrintAbilityPayload(BaseModel):
    event_type: Literal["use_print_ability"] = "use_print_ability"
    ghost_id: str
    ability_id: str
    target_roll_id: str | None = None


class InitiateCommPayload(BaseModel):
    event_type: Literal["initiate_comm"] = "initiate_comm"
    initiator_ghost_id: str
    target_ghost_id: str


class DownloadAbilityPayload(BaseModel):
    event_type: Literal["download_ability"] = "download_ability"
    from_ghost_id: str
    ability_id: str


class DeepScanPayload(BaseModel):
    event_type: Literal["deep_scan"] = "deep_scan"
    target_patient_id: str


class AttemptSeizePayload(BaseModel):
    event_type: Literal["attempt_seize"] = "attempt_seize"
    target_ghost_id: str


class ApplyFragmentPayload(BaseModel):
    event_type: Literal["apply_fragment"] = "apply_fragment"
    ghost_id: str
    color: str  # C/M/Y/K
    value: int = 1


class HPChangePayload(BaseModel):
    event_type: Literal["hp_change"] = "hp_change"
    ghost_id: str
    delta: int
    reason: str = ""


class SectorTransitionPayload(BaseModel):
    event_type: Literal["sector_transition"] = "sector_transition"
    target_sector: str


EventPayload = Annotated[
    Union[
        SessionStartPayload,
        SessionEndPayload,
        PlayerJoinPayload,
        PlayerLeavePayload,
        SkillCheckPayload,
        ExplorePayload,
        AttackPayload,
        DefendPayload,
        UsePrintAbilityPayload,
        InitiateCommPayload,
        DownloadAbilityPayload,
        DeepScanPayload,
        AttemptSeizePayload,
        ApplyFragmentPayload,
        HPChangePayload,
        SectorTransitionPayload,
    ],
    Field(discriminator="event_type"),
]


class GameEvent(BaseModel):
    """Top-level event submitted by a client to the engine."""

    session_id: str
    player_id: str
    payload: EventPayload
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
