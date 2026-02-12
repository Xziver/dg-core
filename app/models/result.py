"""Engine result schemas — output from the engine dispatcher."""

from __future__ import annotations

from pydantic import BaseModel


class DiceRollResult(BaseModel):
    dice_count: int
    dice_type: int
    results: list[int]
    total: int
    difficulty: int
    success: bool
    rerolled: bool = False
    reroll_results: list[int] | None = None


class StateChange(BaseModel):
    entity_type: str  # "ghost", "patient", "game", "game_player", "print_ability"
    entity_id: str
    field: str
    old_value: str | None = None
    new_value: str | None = None


class EngineResult(BaseModel):
    success: bool
    event_type: str
    data: dict = {}
    narrative: str | None = None
    state_changes: list[StateChange] = []
    rolls: list[DiceRollResult] = []
    error: str | None = None
