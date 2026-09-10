"""Check the shared reading of a region off the screen.

`src/en/screen.py` exists so the centre-in-a-band arithmetic is written once. `text_in_region` is the other
half of that: nearly every fork-local handler wants "the box in this band whose text contains this", and
writing the loop out per module is how four near-identical copies appeared.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.screen import in_region, text_in_region  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
BAND = (0.400, 0.400, 0.600, 0.600)


class FakeBox:
    """An OCR box positioned by its centre."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 90, 30
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


class FakeTask:
    """A task holding one OCR pass."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes


class TestTextInRegion(unittest.TestCase):
    """Finding a caption inside a band."""

    def test_finds_a_box_whose_text_contains_the_needle(self):
        box = FakeBox("Free", 0.5, 0.5)
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))

    def test_matches_on_a_substring(self):
        box = FakeBox("SOLD OUT Free refresh", 0.5, 0.5)
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))

    def test_ignores_letter_case(self):
        box = FakeBox("Combatants are limited to 1 piece of Mythic-grade equipment.", 0.5, 0.5)
        self.assertIsNotNone(text_in_region(FakeTask([box]), "mythic", BAND))

    def test_ignores_a_match_outside_the_band(self):
        self.assertIsNone(text_in_region(FakeTask([FakeBox("Free", 0.9, 0.9)]), "Free", BAND))

    def test_returns_none_when_nothing_matches(self):
        self.assertIsNone(text_in_region(FakeTask([FakeBox("Buy", 0.5, 0.5)]), "Free", BAND))

    def test_returns_the_first_match_in_reading_order(self):
        first, second = FakeBox("Free a", 0.45, 0.5), FakeBox("Free b", 0.55, 0.5)
        self.assertIs(first, text_in_region(FakeTask([first, second]), "Free", BAND))

    def test_survives_a_task_with_no_pass_yet(self):
        self.assertIsNone(text_in_region(FakeTask(None), "Free", BAND))

    def test_uses_the_same_containment_rule_as_in_region(self):
        # One rule, so a band that works for a caption works for anything else read off the screen.
        box = FakeBox("Free", 0.5, 0.5)
        self.assertTrue(in_region(box, BAND, WIDTH, HEIGHT))
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))


if __name__ == "__main__":
    unittest.main()
