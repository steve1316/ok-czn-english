"""Check what the picker manages to read off a battle screen.

The two fixtures are the Action Point readout cut out of real frames, and they are deliberately the hardest
pair the captures offer: the zero with the most background bleeding into it, and the lowest positive reading
seen. Anything that widens the gap is fine; anything that closes it fails here first.
"""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import board  # noqa: E402

IMAGES = REPO_ROOT / "tests" / "images"
WIDTH, HEIGHT = 1920, 1080


def fixture(name):
    """Load one of the cut-out readouts.

    Args:
        name: The file's base name.

    Returns:
        The image as the framework hands frames over, in BGR.
    """
    return cv2.imread(str(IMAGES / f"{name}.png"))


class FakeTask:
    """A task holding one frame, which is all the board reading needs."""

    def __init__(self, frame):
        self.frame = frame
        self.height, self.width = frame.shape[:2]


def flat(value):
    """Build a frame of one brightness, for testing the reading rather than the game.

    Args:
        value: The grey level to fill it with.

    Returns:
        A full-size frame.
    """
    return np.full((HEIGHT, WIDTH, 3), value, dtype=np.uint8)


class TestLitFraction(unittest.TestCase):
    """The measurement itself, on the readouts as they really appear."""

    def test_a_zero_is_mostly_dark(self):
        self.assertLess(board.lit_fraction(fixture("action_points_none")), board.LIT_ENOUGH)

    def test_a_positive_reading_is_mostly_lit(self):
        self.assertGreater(board.lit_fraction(fixture("action_points_some")), board.LIT_ENOUGH)

    def test_the_two_are_not_close(self):
        # The digit is drawn bright blue when there are points to spend and thin grey when there are none, so
        # the gap is a property of the game's own rendering rather than a threshold tuned onto noise.
        dark = board.lit_fraction(fixture("action_points_none"))
        lit = board.lit_fraction(fixture("action_points_some"))
        self.assertGreater(lit - dark, 0.05)


class TestActionPoints(unittest.TestCase):
    """The answer the planner actually asks for."""

    def test_an_unlit_readout_means_no_points_left(self):
        self.assertFalse(board.has_action_points(FakeTask(flat(0))))

    def test_a_lit_readout_means_points_remain(self):
        self.assertTrue(board.has_action_points(FakeTask(flat(255))))

    def test_a_frame_that_is_missing_is_not_an_answer(self):
        # `task.frame` is None while capture is between frames, and guessing "no points" there would end a
        # turn that had not finished.
        self.assertTrue(board.has_action_points(FakeTask.__new__(FakeTask)))


if __name__ == "__main__":
    unittest.main()
