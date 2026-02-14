"""Tests for the dice expression parser."""

import pytest

from app.modules.dice.parser import (
    ParsedDice,
    evaluate,
    parse_expression,
    roll_expression,
)


def test_parse_simple_dice():
    parsed = parse_expression("2d6")
    assert parsed.dice_count == 2
    assert parsed.dice_sides == 6
    assert parsed.modifier == 0
    assert parsed.is_cmyk is False


def test_parse_single_die():
    parsed = parse_expression("d100")
    assert parsed.dice_count == 1
    assert parsed.dice_sides == 100


def test_parse_dice_with_positive_modifier():
    parsed = parse_expression("3d8+5")
    assert parsed.dice_count == 3
    assert parsed.dice_sides == 8
    assert parsed.modifier == 5


def test_parse_dice_with_negative_modifier():
    parsed = parse_expression("2d6-2")
    assert parsed.dice_count == 2
    assert parsed.modifier == -2


def test_parse_keep_highest():
    parsed = parse_expression("4d10k2")
    assert parsed.dice_count == 4
    assert parsed.dice_sides == 10
    assert parsed.keep_highest == 2


def test_parse_cmyk_simple():
    parsed = parse_expression("c", cmyk_values={"C": 3, "M": 1, "Y": 0, "K": 2})
    assert parsed.is_cmyk is True
    assert parsed.cmyk_color == "C"
    assert parsed.dice_count == 3
    assert parsed.dice_sides == 6


def test_parse_cmyk_with_modifier():
    parsed = parse_expression("m+2", cmyk_values={"C": 3, "M": 1, "Y": 0, "K": 2})
    assert parsed.is_cmyk is True
    assert parsed.cmyk_color == "M"
    assert parsed.dice_count == 1
    assert parsed.modifier == 2


def test_parse_cmyk_no_values():
    parsed = parse_expression("k")
    assert parsed.is_cmyk is True
    assert parsed.cmyk_color == "K"
    assert parsed.dice_count == 0


def test_parse_invalid_expression():
    with pytest.raises(ValueError):
        parse_expression("abc123")


def test_parse_empty_expression():
    with pytest.raises(ValueError):
        parse_expression("")


def test_evaluate_basic():
    parsed = ParsedDice(original="2d6", dice_count=2, dice_sides=6)
    result = evaluate(parsed)
    assert len(result.individual_rolls) == 2
    assert all(1 <= r <= 6 for r in result.individual_rolls)
    assert result.total == sum(result.individual_rolls)


def test_evaluate_keep_highest():
    parsed = ParsedDice(
        original="4d6k2", dice_count=4, dice_sides=6, keep_highest=2
    )
    result = evaluate(parsed)
    assert len(result.individual_rolls) == 4
    assert result.kept_rolls is not None
    assert len(result.kept_rolls) == 2
    assert result.subtotal == sum(result.kept_rolls)


def test_roll_expression_convenience():
    result = roll_expression("2d6+3")
    assert len(result.individual_rolls) == 2
    assert result.modifier == 3
    assert result.total == result.subtotal + 3


def test_keep_more_than_rolled_raises():
    with pytest.raises(ValueError, match="Cannot keep"):
        parse_expression("2d6k5")
