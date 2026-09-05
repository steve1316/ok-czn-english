"""Check that a run speaks up when it starts, when it finishes, and when it is stuck."""

import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import notify  # noqa: E402


class FakeTask:
    """A mode, recording what it was asked to announce."""

    def __init__(self, rounds=0, wins=0, bosses=0):
        self.name = "自动卡厄思模式"
        self.node_status = {
            notify.ROUNDS: rounds,
            notify.WINS: wins,
            notify.BOSSES: bosses,
        }
        self.logged = []
        self.notifications = []
        self.enables = 0

    def log_info(self, message, notify=False):
        self.logged.append(message)

    def notification(self, message, title=None, error=False, tray=False, **kwargs):
        self.notifications.append({"message": message, "title": title, "tray": tray})

    def enable(self):
        self.enables += 1


def finishes(task, wins_it=True):
    """Stand in for upstream's expedition result page, which scores the run and clears its status.

    Args:
        task: The task being scored.
        wins_it: Whether the run counted as a success.

    Returns:
        The wrapped handler's own return value.
    """
    def handle_expedition_result(task):
        task.node_status[notify.ROUNDS] += 1
        if wins_it:
            task.node_status[notify.WINS] += 1
        # Upstream clears the per-run status before it returns, which is what takes the floor with it.
        task.node_status[notify.BOSSES] = 0
        return False

    return notify.finishing(handle_expedition_result)(task)


class TestNotify(unittest.TestCase):

    def test_starting_a_run_announces_it(self):
        task = FakeTask()
        task.enable = notify.starting(task.enable, task)
        task.enable()
        self.assertEqual(1, task.enables)
        self.assertEqual(["Run started."], [note["message"] for note in task.notifications])

    def test_the_notification_is_titled_with_the_mode(self):
        """The title is run through the app catalog on the way out, which puts it in English."""
        task = FakeTask()
        notify.starting(task.enable, task)()
        self.assertEqual("自动卡厄思模式", task.notifications[0]["title"])

    def test_every_notification_reaches_windows(self):
        """Without `tray`, it only shows inside the app, which defeats the point of notifying."""
        task = FakeTask()
        notify.starting(task.enable, task)()
        self.assertTrue(task.notifications[0]["tray"])

    def test_a_finished_run_reports_the_floor_it_reached(self):
        """The floor has to be read before the handler runs, because the handler clears it."""
        task = FakeTask(rounds=2, wins=1, bosses=3)
        finishes(task)
        self.assertEqual(["Run finished on floor 4. 2 of 3 runs have succeeded."],
                         [note["message"] for note in task.notifications])

    def test_a_lost_run_is_reported_too(self):
        task = FakeTask(rounds=0, wins=0, bosses=0)
        finishes(task, wins_it=False)
        self.assertEqual(["Run finished on floor 1. 0 of 1 runs have succeeded."],
                         [note["message"] for note in task.notifications])

    def test_a_page_that_scored_nothing_says_nothing(self):
        """The handler runs on every frame that shows the page, and only one of them counts a round."""
        task = FakeTask(rounds=1)
        notify.finishing(lambda task: False)(task)
        self.assertEqual([], task.notifications)

    def test_a_screen_stuck_past_the_threshold_is_reported(self):
        task = FakeTask()
        task._last_change_time = time.time() - (notify.STUCK_SECONDS + 5)
        notify.stuck(lambda task: False)(task)
        self.assertEqual(1, len(task.notifications))
        self.assertIn("Stuck on the same screen", task.notifications[0]["message"])

    def test_a_screen_stuck_briefly_is_left_to_upstream(self):
        """Upstream already clicks its way out from ten seconds, so a short spell is not worth a toast."""
        task = FakeTask()
        task._last_change_time = time.time() - 15
        notify.stuck(lambda task: False)(task)
        self.assertEqual([], task.notifications)

    def test_one_stuck_screen_only_reports_once(self):
        """The handler runs every frame, so without this it would notify several times a second."""
        task = FakeTask()
        task._last_change_time = time.time() - (notify.STUCK_SECONDS + 5)
        handler = notify.stuck(lambda task: False)
        for _ in range(5):
            handler(task)
        self.assertEqual(1, len(task.notifications))

    def test_a_screen_that_starts_moving_again_can_report_next_time(self):
        task = FakeTask()
        handler = notify.stuck(lambda task: False)
        task._last_change_time = time.time() - (notify.STUCK_SECONDS + 5)
        handler(task)
        task._last_change_time = time.time()
        handler(task)
        task._last_change_time = time.time() - (notify.STUCK_SECONDS + 5)
        handler(task)
        self.assertEqual(2, len(task.notifications))

    def test_a_task_with_no_stuck_detection_is_left_alone(self):
        task = FakeTask()
        notify.stuck(lambda task: False)(task)
        self.assertEqual([], task.notifications)

    def test_the_wrapped_handler_keeps_its_answer(self):
        """Position in the handler list is the priority scheme, so the return value decides what runs next."""
        self.assertTrue(notify.stuck(lambda task: True)(FakeTask()))
        self.assertFalse(notify.stuck(lambda task: False)(FakeTask()))

    def test_the_replacement_is_named_apart_from_the_original(self):
        """`handlers.replace` matches by name, so a wrapper named after the original would wrap itself."""
        self.assertEqual("handle_stuck_log_announcing", notify.stuck(lambda task: False).__name__)
        self.assertEqual("handle_expedition_result_announcing", notify.finishing(lambda task: False).__name__)


if __name__ == "__main__":
    unittest.main()
