"""Check when the bot buys another dice roll and when it takes the loss.

`src/en/dice.py` spends a limited currency, so the failure modes are asymmetric: declining a reroll that was
affordable costs one event, while rerolling when it should not can drain the budget or spin on a screen. The
policy is a pure function for that reason, and everything below drives it directly.

The box lists are the exact OCR of the failure and success screens from the 2026-09-04 Chaos run.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.dice import (  # noqa: E402
    REROLL_CAP, REROLL_COST, find_currency, find_reroll_button, parse_currency, should_reroll,
)

WIDTH, HEIGHT = 1920, 1080


class FakeBox:
    """An OCR box, carrying only what the reroll code reads off one."""

    def __init__(self, name, x, y, width=90, height=30):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height


# The failure screen, as OCR read it: 25/25十, Dexterous, 14, 失败, Reroll, 下一步.
FAILURE_BOXES = [
    FakeBox("25/25十", 1720, 95),
    FakeBox("Dexterous", 880, 165),
    FakeBox("14", 940, 250),
    FakeBox("失败", 905, 725),
    FakeBox("Reroll", 600, 960),
    FakeBox("下一步", 1220, 960),
]

# The success screen has no Reroll button at all, and is claimed by handle_close_page long before us.
SUCCESS_BOXES = [
    FakeBox("25/25+", 1720, 95),
    FakeBox("Roll", 900, 165),
    FakeBox("7", 940, 250),
    FakeBox("点击屏幕关闭窗口", 830, 780),
]


class TestDiceReroll(unittest.TestCase):

    def test_currency_parses_through_the_merged_glyph(self):
        """The + button merges into the same box, read as either "+" or "十"."""
        self.assertEqual((25, 25), parse_currency("25/25十"))
        self.assertEqual((25, 25), parse_currency("25/25+"))
        self.assertEqual((23, 25), parse_currency("23/25"))
        self.assertEqual((25, 25), parse_currency("25 / 25"))

    def test_text_that_is_not_a_counter_parses_to_nothing(self):
        for text in ("Reroll", "14", "", None, "Dexterous"):
            with self.subTest(text=text):
                self.assertIsNone(parse_currency(text))

    def test_the_counter_is_read_off_the_failure_screen(self):
        self.assertEqual((25, 25), find_currency(FAILURE_BOXES, WIDTH, HEIGHT))

    def test_a_health_bar_is_not_mistaken_for_the_counter(self):
        """Health reads exactly like a counter, which is why only the top right corner is searched."""
        health = [FakeBox("2536/2536", 300, 40)]
        self.assertIsNone(find_currency(health, WIDTH, HEIGHT))

    def test_the_reroll_button_is_found_by_its_text(self):
        """Found, not assumed: clicking a fixed coordinate would buy something unseen."""
        self.assertIs(FAILURE_BOXES[4], find_reroll_button(FAILURE_BOXES))

    def test_the_success_screen_offers_no_reroll(self):
        self.assertIsNone(find_reroll_button(SUCCESS_BOXES))

    def test_the_first_failure_is_rerolled(self):
        self.assertTrue(should_reroll(0, 25))

    def test_the_cap_is_a_hard_ceiling(self):
        self.assertTrue(should_reroll(REROLL_CAP - 1, 25))
        self.assertFalse(should_reroll(REROLL_CAP, 25))
        self.assertFalse(should_reroll(REROLL_CAP + 1, 25))

    def test_an_unaffordable_reroll_is_never_attempted(self):
        """A reroll costs 2, so 0 and 1 in hand cannot pay for one."""
        for current in range(REROLL_COST):
            with self.subTest(current=current):
                self.assertFalse(should_reroll(0, current))
        self.assertTrue(should_reroll(0, REROLL_COST))

    def test_the_budget_runs_out_before_the_currency_does(self):
        """Five rerolls at 2 each is 10 of 25, so the cap is what stops it, not the wallet."""
        self.assertTrue(should_reroll(REROLL_CAP - 1, 25 - (REROLL_CAP - 1) * REROLL_COST))
        self.assertFalse(should_reroll(REROLL_CAP, 25 - REROLL_CAP * REROLL_COST))


if __name__ == "__main__":
    unittest.main()
