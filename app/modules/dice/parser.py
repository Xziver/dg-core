"""Dice expression parser — supports NdM, NdM+X, NdMkK, CMYK references."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


@dataclass
class ParsedDice:
    """Result of parsing a dice expression."""

    original: str
    dice_count: int  # 0 if CMYK with no values provided
    dice_sides: int  # default 6 for CMYK
    modifier: int = 0
    keep_highest: int | None = None
    is_cmyk: bool = False
    cmyk_color: str | None = None


@dataclass
class DiceExpressionResult:
    """Full result of evaluating a dice expression."""

    expression: str
    individual_rolls: list[int] = field(default_factory=list)
    kept_rolls: list[int] | None = None
    subtotal: int = 0
    modifier: int = 0
    total: int = 0


_CMYK_PATTERN = re.compile(
    r"^([cmyk])\s*([+-]\s*\d+)?$",
    re.IGNORECASE,
)

_DICE_PATTERN = re.compile(
    r"^(\d*)d(\d+)"  # NdM
    r"(?:k(\d+))?"  # optional kK
    r"(?:\s*([+-])\s*(\d+))?$",  # optional +X or -X
    re.IGNORECASE,
)


def parse_expression(
    expr: str,
    cmyk_values: dict[str, int] | None = None,
    default_dice_sides: int = 6,
) -> ParsedDice:
    """Parse a dice expression string into a ParsedDice.

    Supported formats:
        NdM        - e.g. 2d6
        NdM+X      - e.g. 2d6+3
        NdM-X      - e.g. 2d6-2
        NdMkK      - e.g. 4d10k2 (keep highest K)
        dM         - e.g. d100 (shorthand for 1dM)
        c/m/y/k    - CMYK attribute reference (resolved to Nd{sides})
        c+2, m-1   - CMYK with modifier

    Args:
        expr: The expression string.
        cmyk_values: Optional dict {"C": 3, "M": 1, ...} for CMYK resolution.
        default_dice_sides: Default die type for CMYK references (default 6).

    Returns:
        ParsedDice with all parsed components.

    Raises:
        ValueError: If the expression cannot be parsed.
    """
    expr = expr.strip()
    if not expr:
        raise ValueError("Empty dice expression")

    # Try CMYK pattern first
    cmyk_match = _CMYK_PATTERN.match(expr)
    if cmyk_match:
        color = cmyk_match.group(1).upper()
        mod_str = cmyk_match.group(2)
        modifier = int(mod_str.replace(" ", "")) if mod_str else 0
        dice_count = 0
        if cmyk_values:
            dice_count = cmyk_values.get(color, 0)
        return ParsedDice(
            original=expr,
            dice_count=dice_count,
            dice_sides=default_dice_sides,
            modifier=modifier,
            is_cmyk=True,
            cmyk_color=color,
        )

    # Try standard dice pattern
    dice_match = _DICE_PATTERN.match(expr)
    if dice_match:
        count_str = dice_match.group(1)
        sides = int(dice_match.group(2))
        keep_str = dice_match.group(3)
        sign = dice_match.group(4)
        mod_val = dice_match.group(5)

        dice_count = int(count_str) if count_str else 1
        keep_highest = int(keep_str) if keep_str else None
        modifier = 0
        if sign and mod_val:
            modifier = int(mod_val) if sign == "+" else -int(mod_val)

        if keep_highest is not None and keep_highest > dice_count:
            raise ValueError(
                f"Cannot keep {keep_highest} dice from {dice_count} rolls"
            )

        return ParsedDice(
            original=expr,
            dice_count=dice_count,
            dice_sides=sides,
            modifier=modifier,
            keep_highest=keep_highest,
        )

    raise ValueError(f"Invalid dice expression: {expr}")


def evaluate(parsed: ParsedDice) -> DiceExpressionResult:
    """Roll dice according to a ParsedDice and return the full result."""
    individual_rolls = [
        random.randint(1, parsed.dice_sides) for _ in range(max(parsed.dice_count, 0))
    ]

    kept_rolls = None
    if parsed.keep_highest is not None and individual_rolls:
        sorted_rolls = sorted(individual_rolls, reverse=True)
        kept_rolls = sorted_rolls[: parsed.keep_highest]
        subtotal = sum(kept_rolls)
    else:
        subtotal = sum(individual_rolls)

    total = subtotal + parsed.modifier

    return DiceExpressionResult(
        expression=parsed.original,
        individual_rolls=individual_rolls,
        kept_rolls=kept_rolls,
        subtotal=subtotal,
        modifier=parsed.modifier,
        total=total,
    )


def roll_expression(
    expr: str,
    cmyk_values: dict[str, int] | None = None,
    default_dice_sides: int = 6,
) -> DiceExpressionResult:
    """Convenience: parse + evaluate in one call."""
    parsed = parse_expression(expr, cmyk_values, default_dice_sides)
    return evaluate(parsed)
