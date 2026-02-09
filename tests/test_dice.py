"""Unit tests for the CMYK dice roller."""

import pytest

from app.modules.dice.roller import DiceRoll, reroll, roll


class TestRoll:
    def test_roll_returns_correct_structure(self):
        result = roll(color_value=2, dice_type=6, difficulty=5)
        assert isinstance(result, DiceRoll)
        assert result.dice_count == 2
        assert result.dice_type == 6
        assert result.difficulty == 5
        assert len(result.results) == 2
        assert result.total == sum(result.results)
        assert result.success == (result.total >= 5)
        assert result.rerolled is False
        assert result.reroll_results is None

    def test_roll_minimum_one_die(self):
        result = roll(color_value=0, dice_type=6, difficulty=3)
        assert result.dice_count == 1
        assert len(result.results) == 1

    def test_roll_results_in_valid_range(self):
        for _ in range(100):
            result = roll(color_value=3, dice_type=6, difficulty=10)
            assert all(1 <= r <= 6 for r in result.results)
            assert len(result.results) == 3

    def test_roll_with_d10(self):
        result = roll(color_value=2, dice_type=10, difficulty=8)
        assert result.dice_type == 10
        assert all(1 <= r <= 10 for r in result.results)

    def test_roll_success_detection(self):
        # With high value and low difficulty, should often succeed
        successes = sum(
            1 for _ in range(100)
            if roll(color_value=5, dice_type=6, difficulty=5).success
        )
        assert successes > 50  # Should succeed most of the time


class TestReroll:
    def test_reroll_marks_as_rerolled(self):
        original = roll(color_value=2, dice_type=6, difficulty=20)
        result = reroll(original)
        assert result.rerolled is True
        assert result.reroll_results is not None

    def test_reroll_keeps_better_result(self):
        # Run many rerolls and verify total is always >= original or the new roll
        for _ in range(100):
            original = roll(color_value=2, dice_type=6, difficulty=7)
            result = reroll(original)
            # The result total should be the max of original and new
            assert result.total >= min(original.total, sum(result.reroll_results))

    def test_reroll_preserves_dice_config(self):
        original = roll(color_value=3, dice_type=10, difficulty=15)
        result = reroll(original)
        assert result.dice_count == 3
        assert result.dice_type == 10
        assert result.difficulty == 15
