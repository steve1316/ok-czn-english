"""Check that the Faint Memory warning is cancelled and the reward under it skipped, never confirmed.

The warning boxes are the OCR of the dialog from the 2026-09-04 Chaos run, where upstream clicked Confirm on it.
"""

import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.memory_limit import STATE, handle_memory_limit  # noqa: E402
from tests.fakes import HEIGHT, WIDTH, FakeBox  # noqa: E402

SKIP_BUTTON = FakeBox("跳过", 0.951, 0.930, units="fraction")
# The reward screen as it sits under the dialog: the cards, and Skip in the bottom right.
REWARD_SCREEN = [
    FakeBox("Domain of Voracity", 0.272, 0.250, width=300, units="fraction"),
    FakeBox("Epiphany: Vytor", 0.501, 0.887, width=350, units="fraction"),
    SKIP_BUTTON,
]
CANCEL_BUTTON = FakeBox("取消", 0.347, 0.632, units="fraction")
WARNING_DIALOG = REWARD_SCREEN + [
    FakeBox("Selecting the reward will cause Faint Memory to exceed its limit.", 0.500, 0.392, width=1000, units="fraction"),
    FakeBox("Upon exceeding the limit, part of the Save Data will be altered.", 0.500, 0.432, width=960, units="fraction"),
    FakeBox("Faint Memory", 0.411, 0.525, width=180, units="fraction"),
    FakeBox("100 / 90 points", 0.643, 0.525, width=180, units="fraction"),
    CANCEL_BUTTON,
    FakeBox("确认", 0.666, 0.632, units="fraction"),
]


class FakeTask:
    """A mode showing one frame and recording the boxes clicked on it."""

    def __init__(self, boxes):
        self.all_texts = boxes
        self.width, self.height = WIDTH, HEIGHT
        self.clicked = []

    def click_box(self, box, *args, **kwargs):
        self.clicked.append(box)

    def log_info(self, message):
        pass

    def sleep(self, seconds):
        pass


class TestMemoryLimit(unittest.TestCase):

    def test_the_warning_is_cancelled_then_the_reward_skipped(self):
        """Confirm would alter the save data, and leaving the reward screen up would pick the card again."""
        task = FakeTask(WARNING_DIALOG)
        self.assertTrue(handle_memory_limit(task))
        self.assertEqual([CANCEL_BUTTON], task.clicked)

        task.all_texts = REWARD_SCREEN
        self.assertTrue(handle_memory_limit(task))
        self.assertEqual([CANCEL_BUTTON, SKIP_BUTTON], task.clicked)

        # The Skip is owed once, so the next reward screen is left to upstream.
        self.assertFalse(handle_memory_limit(task))

    def test_a_skip_long_after_the_cancel_is_left_alone(self):
        task = FakeTask(REWARD_SCREEN)
        setattr(task, STATE, time.monotonic() - 60)
        self.assertFalse(handle_memory_limit(task))
        self.assertEqual([], task.clicked)

    def test_the_warning_is_held_even_when_cancel_was_not_read(self):
        """Declining the frame would hand it to `handle_center_confirm`, which clicks Confirm."""
        task = FakeTask([box for box in WARNING_DIALOG if box is not CANCEL_BUTTON])
        self.assertTrue(handle_memory_limit(task))
        self.assertEqual([], task.clicked)


if __name__ == "__main__":
    unittest.main()
