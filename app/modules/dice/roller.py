"""CMYK dice roller for Digital Ghost."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class DiceRoll:
    dice_count: int
    dice_type: int
    results: list[int]
    total: int
    difficulty: int
    success: bool
    rerolled: bool = False
    reroll_results: list[int] | None = None


def roll(color_value: int, dice_type: int, difficulty: int) -> DiceRoll:
    """Roll dice based on a CMYK color value.

    Args:
        color_value: The CMYK attribute value (number of dice to roll).
        dice_type: Number of sides per die (e.g. 6, 10, 20).
        difficulty: Target number the total must meet or exceed.

    Returns:
        A DiceRoll with the outcome.
    """
    count = max(color_value, 1)
    results = [random.randint(1, dice_type) for _ in range(count)]
    total = sum(results)
    return DiceRoll(
        dice_count=count,
        dice_type=dice_type,
        results=results,
        total=total,
        difficulty=difficulty,
        success=total >= difficulty,
    )


def reroll(original: DiceRoll) -> DiceRoll:
    """Re-roll using a print ability (one extra chance).

    Keeps the better result between original and new roll.
    """
    new_results = [random.randint(1, original.dice_type) for _ in range(original.dice_count)]
    new_total = sum(new_results)

    # Keep the better outcome
    if new_total >= original.total:
        return DiceRoll(
            dice_count=original.dice_count,
            dice_type=original.dice_type,
            results=new_results,
            total=new_total,
            difficulty=original.difficulty,
            success=new_total >= original.difficulty,
            rerolled=True,
            reroll_results=new_results,
        )
    else:
        return DiceRoll(
            dice_count=original.dice_count,
            dice_type=original.dice_type,
            results=original.results,
            total=original.total,
            difficulty=original.difficulty,
            success=original.total >= original.difficulty,
            rerolled=True,
            reroll_results=new_results,
        )
