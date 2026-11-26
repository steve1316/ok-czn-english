"""Check when the bot buys another dice roll and when it takes the loss.

`src/en/dice.py` spends a limited currency, so the failure modes are asymmetric: declining a reroll that was
affordable costs one event, while rerolling when it should not can drain the budget or spin on a screen. The
policy is a pure function for that reason, and everything below drives it directly.

The box lists are the exact OCR of the failure and success screens from the 2026-09-04 Chaos run.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402

from src.en import dice, handlers  # noqa: E402
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

    def area(self):
        return self.width * self.height


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


# Upstream's Next button on the failure screen.
NEXT = (0.665, 0.899)
# A box OCR returned with no text, smaller than the caption and over the point both gates read.
EMPTY_RESULT = FakeBox("", 940, 725, width=40, height=25)


class FakeTask:
    """A mode recording the taps a handler asks for."""

    def __init__(self, boxes):
        self.all_texts = boxes
        self.width, self.height = WIDTH, HEIGHT
        self.clicked = []

    def log_info(self, message):
        pass

    def click_box(self, box):
        self.clicked.append(box.name)

    def sleep(self, seconds):
        pass


def claim(boxes):
    """Run a mode's handler list, as `dice.install` leaves it, over one screen.

    The list holds upstream's real `handle_negotiation` behind a stand-in module, so the install wraps the stand-in
    and not the real `utils`, and only this list is edited.

    Args:
        boxes: Every OCR box on screen.

    Returns:
        The name of the handler that took the frame (None when none did), and the task.
    """
    def handle_negotiation(task):
        return utils.handle_negotiation(task)

    stand_in = types.SimpleNamespace(find_box_at_point=utils.find_box_at_point, handle_negotiation=handle_negotiation)
    page_handlers = [handle_negotiation]
    task = FakeTask(boxes)
    record = lambda task_, x, y: task_.clicked.append((x, y))  # noqa: E731
    with handlers.standing_in(handlers, each_list=lambda: iter([("fake_mode_for_dice_test", page_handlers)])):
        dice.install(stand_in)
        with handlers.standing_in(utils, _move_and_click=record):
            claimed = next((handler.__name__ for handler in page_handlers if handler(task)), None)
    assert [handler.__name__ for handler in page_handlers] == ["handle_dice_reroll", "handle_negotiation"]
    return claimed, task


class TestEmptyResultCaption(unittest.TestCase):
    """An empty name is in every string, so `name in "失败"` alone reads an empty box as a failed roll."""

    def test_an_empty_result_box_buys_no_reroll(self):
        """Reroll and the counter are on screen, so only the caption test stands between this and a spend."""
        task = FakeTask([EMPTY_RESULT, FakeBox("Reroll", 600, 960), FakeBox("25/25+", 1720, 95)])
        self.assertFalse(dice.make_handler(utils)(task))
        self.assertEqual([], task.clicked)

    def test_an_empty_result_box_takes_no_next_click(self):
        for name in ("", "  "):
            with self.subTest(name=name):
                claimed, task = claim([FakeBox(name, 940, 725, width=40, height=25)])
                self.assertIsNone(claimed)
                self.assertEqual([], task.clicked)

    def test_the_failure_caption_still_clicks_next(self):
        """With no Reroll button the reroll handler declines, and upstream's Next takes the loss."""
        claimed, task = claim([box for box in FAILURE_BOXES if box.name != "Reroll"])
        self.assertEqual("handle_negotiation", claimed)
        self.assertEqual([NEXT], task.clicked)


if __name__ == "__main__":
    unittest.main()
