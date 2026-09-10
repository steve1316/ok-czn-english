"""Check that a new run starts its own stuck clock instead of inheriting the last one's.

Upstream decides a screen has frozen by keeping two things on the task, and the task outlives the run - the
Start button re-enables the same object. Nothing cleared them between runs, so the clock kept counting through
however long the app sat stopped, and the first frame of a new run could report a minute of frozen screen.

These run upstream's own detector rather than a stand-in for it, because the bug is in what it remembers.
"""

import sys
import time
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402

from src.en import notify, stuck  # noqa: E402

# Small enough to keep the detector's resize and diff cheap, large enough to survive dividing by four.
SHAPE = (60, 80, 3)
# Comfortably past the ten seconds upstream starts clicking its way out at.
FROZEN_FOR = 44


def screen(shade=0):
    """Build a flat frame the detector can compare against another.

    Args:
        shade: The grey level to fill it with. Two different shades read as a changed screen.

    Returns:
        A BGR frame.
    """
    return np.full(SHAPE, shade, dtype=np.uint8)


class FakeTask:
    """A mode showing one frame, recording whether its own `enable` ran."""

    def __init__(self):
        self.frame = screen()
        self.enables = 0

    def enable(self):
        self.enables += 1


def watched(task, seconds=FROZEN_FOR):
    """Put a task in the state a run leaves behind: the detector seeded, the screen unchanged for a while.

    Args:
        task: The task to seed.
        seconds: How long ago the picture last changed.
    """
    utils.is_frame_stuck(task)
    setattr(task, stuck.CLOCK, time.time() - seconds)


def stuck_now(task):
    """Ask upstream's detector whether it considers the screen frozen.

    Args:
        task: The task to check.

    Returns:
        True when the screen counts as stuck.
    """
    return utils.is_frame_stuck(task, stuck_threshold_seconds=10)


class TestStuckClock(unittest.TestCase):

    def test_a_screen_that_never_changes_is_reported_as_stuck(self):
        """Upstream's behaviour both ways round: the point of the detector, and the bug this file is about.

        Nothing distinguishes a screen genuinely frozen for 44 seconds from a run restarted on the screen the
        last one left up, which is why the clock has to be cleared at the run boundary instead.
        """
        task = FakeTask()
        watched(task)
        self.assertTrue(stuck_now(task))

    def test_a_screen_that_changed_is_not_stuck(self):
        task = FakeTask()
        watched(task)
        task.frame = screen(255)
        self.assertFalse(stuck_now(task))

    def test_a_new_run_does_not_inherit_the_last_runs_clock(self):
        task = FakeTask()
        watched(task)
        stuck.forget(task)
        self.assertFalse(stuck_now(task))

    def test_the_new_run_can_still_find_its_own_screen_stuck(self):
        """Forgetting restarts the clock, it does not switch the detector off."""
        task = FakeTask()
        watched(task)
        stuck.forget(task)
        watched(task)
        self.assertTrue(stuck_now(task))

    def test_forgetting_drops_the_picture_as_well_as_the_clock(self):
        """A picture kept from the last run would have the new run's first frame compared against it."""
        task = FakeTask()
        watched(task)
        stuck.forget(task)
        for name in stuck.CACHE:
            self.assertFalse(hasattr(task, name), name)

    def test_forgetting_before_the_detector_has_ever_run_is_safe(self):
        """Every mode is enabled before it has a frame, and a mode that never sticks never seeds the pair."""
        stuck.forget(FakeTask())

    def test_starting_a_run_forgets_the_last_one(self):
        task = FakeTask()
        watched(task)
        task.enable = stuck.restarting(task.enable, task)
        task.enable()
        self.assertEqual(1, task.enables)
        for name in stuck.CACHE:
            self.assertFalse(hasattr(task, name), name)


class TestStartButtonReachesIt(unittest.TestCase):
    """`apply()` has to land the reset on the reference the Start button actually reaches.

    Three things wrap `enable` between here and the button. `src/en/notify.py` wraps it at the same seam, and
    `src/en/shell.py` takes its own reference later still and calls that from the run loop, so a reset
    installed at the wrong moment would be quietly stepped over rather than fail.
    """

    @classmethod
    def setUpClass(cls):
        from ok.task.task import BaseTask, TriggerTask
        cls.BaseTask = BaseTask
        cls.original_load_config = BaseTask.load_config
        # Stood in for before the patches wrap it, so a bare fake does not need the framework's own config.
        BaseTask.load_config = lambda task: None
        # Both are once-per-process, so they are installed once for the class rather than once per test.
        notify.apply()
        stuck.apply()
        cls.TriggerTask = TriggerTask

    @classmethod
    def tearDownClass(cls):
        cls.BaseTask.load_config = cls.original_load_config

    def setUp(self):
        run = self.run_order = []

        class FakeMode(self.TriggerTask):
            def __init__(self):
                self.name = "mode"

            def enable(self):
                run.append(("enable", tuple(name for name in stuck.CACHE if hasattr(self, name))))

            def log_info(self, message, notify=False):
                run.append(("log", message))

            def notification(self, *args, **kwargs):
                pass

        self.task = FakeMode()

    def start(self):
        """Take a task through load, the window's late capture of `enable`, and the Start button."""
        # Set rather than seeded through the detector: a real `TriggerTask` reads `frame` off its executor,
        # and all this needs is the leftovers a finished run would have left on the object.
        for name in stuck.CACHE:
            setattr(self.task, name, "left over from the last run")
        self.BaseTask.load_config(self.task)
        # What `src/en/shell.py` captures once the modes move to the Tasks tab, long after the config loads.
        captured = self.task.enable
        captured()

    def test_the_clock_is_cleared_before_the_run_starts(self):
        self.start()
        self.assertEqual(("enable", ()), self.run_order[0])

    def test_the_run_is_still_announced_afterwards(self):
        """The same seam carries the start-of-run notification, which must survive sharing it."""
        self.start()
        self.assertIn(("log", "Run started."), self.run_order)


if __name__ == "__main__":
    unittest.main()
