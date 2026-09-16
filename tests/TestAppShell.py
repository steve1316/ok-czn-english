"""Check that the game modes run from a Start button, that the scaffold tabs are gone, and that the list draws."""

import os
import sys
import types
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ok.task.exceptions import TaskDisabledException  # noqa: E402

from src.config import config  # noqa: E402
from src.en import dashboard, layout, shell  # noqa: E402
from src.en.framework import import_ui  # noqa: E402

# How many passes the fake executor allows before it stops the loop, standing in for a press of Stop.
PASSES = 3


class FakeSignal:
    """One of the framework's Qt signals, recording what was emitted rather than delivering it."""

    def __init__(self):
        self.emitted = []

    def emit(self, value):
        self.emitted.append(value)


class FakeCommunicate:
    """The framework's signal hub, reduced to the one signal the card listens on."""

    def __init__(self):
        self.task = FakeSignal()


class FakeExecutor:
    """The task executor, counting the calls the loop depends on and stopping it on cue."""

    def __init__(self):
        self.trigger_tasks = []
        self.onetime_tasks = []
        self.resets = 0
        self.sleeps = []
        self.paused = False

    def get_all_tasks(self):
        return self.onetime_tasks + self.trigger_tasks

    def reset_scene(self):
        self.resets += 1
        if self.resets >= PASSES:
            raise TaskDisabledException()

    def pause(self):
        self.paused = True


class FakeTask:
    """A mode, holding only what the move touches."""

    def __init__(self, executor, trigger_interval=1):
        self.executor = executor
        self.trigger_interval = trigger_interval
        self.passes = 0
        self.enables = 0
        self.is_custom = True
        self._enabled = True
        self._paused = False
        # Set to stop the mode from inside its own run, the way a round limit or a finished story does.
        self.stop_after = None
        # Set to change the pace from inside a pass, the way the battle recorder does on a battle screen.
        self.hurry_to = None

    @property
    def enabled(self):
        return self._enabled

    def enable(self):
        self.enables += 1
        self._enabled = True

    def run(self):
        self.passes += 1
        if self.hurry_to is not None:
            self.trigger_interval = self.hurry_to
        if self.passes == self.stop_after:
            self._enabled = False

    def sleep(self, seconds):
        self.executor.sleeps.append(seconds)


class ChaosMode(FakeTask):
    pass


class SortieMode(FakeTask):
    pass


class StoryMode(FakeTask):
    pass


class TestTrigger(FakeTask):
    pass


class GetMengbian(FakeTask):
    pass


class FakeTaskManager:
    """The task manager, holding only the flag that decides whether the Script tab is built."""

    def __init__(self):
        self.has_custom = True


def moved(*task_classes, interval=1):
    """Run the restructure over a set of tasks and hand back what it worked on.

    Args:
        task_classes: The classes to place in the trigger list, in order.
        interval: The trigger interval each of them asks for.

    Returns:
        An `(executor, task_manager, tasks)` triple.
    """
    executor = FakeExecutor()
    tasks = [task_class(executor, trigger_interval=interval) for task_class in task_classes]
    executor.trigger_tasks.extend(tasks)
    task_manager = FakeTaskManager()
    shell.restructure(executor, task_manager, FakeCommunicate())
    return executor, task_manager, tasks


class TestAppShell(unittest.TestCase):

    def test_the_modes_move_to_the_tab_that_has_start_buttons(self):
        """`TaskCard` draws a switch for anything left in the trigger list, and buttons for this one."""
        executor, _, tasks = moved(ChaosMode, SortieMode, StoryMode)
        self.assertEqual([], executor.trigger_tasks)
        self.assertEqual(tasks, executor.onetime_tasks)

    def test_the_untranslated_upstream_tasks_are_hidden_where_they_stand(self):
        """`ok_tasks/` stays byte-identical to upstream, so they are hidden rather than removed."""
        executor, _, tasks = moved(TestTrigger, GetMengbian)
        for task in tasks:
            self.assertFalse(task.visible)
        self.assertEqual(tasks, executor.trigger_tasks)

    def test_a_mode_upstream_renames_is_still_promoted(self):
        """Selecting by list membership rather than by name is what keeps a rename from stranding a mode."""
        class SomeNewMode(FakeTask):
            pass

        executor, _, tasks = moved(SomeNewMode)
        self.assertEqual(tasks, executor.onetime_tasks)

    def test_the_script_and_template_tabs_are_turned_off(self):
        _, task_manager, _ = moved(ChaosMode)
        self.assertFalse(task_manager.has_custom)

    def test_the_edit_button_is_dropped_with_the_tab_it_opens(self):
        """`TaskCard` builds it from `is_custom`, and it opens a Script tab that no longer exists."""
        _, _, tasks = moved(ChaosMode)
        self.assertFalse(tasks[0].is_custom)

    def test_a_mode_left_enabled_by_a_crash_does_not_start_itself(self):
        """The executor runs any enabled one-time task without being asked, so this has to be cleared."""
        _, _, tasks = moved(ChaosMode)
        self.assertFalse(tasks[0]._enabled)

    def test_the_single_pass_run_repeats_until_the_task_is_stopped(self):
        """Upstream's run handles one frame, and the executor no longer calls it again."""
        executor, _, tasks = moved(ChaosMode)
        task = tasks[0]
        with self.assertRaises(TaskDisabledException):
            task.run()
        self.assertEqual(PASSES, task.passes)
        # Every pass drops the cached frame, since the executor hands back the last screenshot until cleared.
        self.assertEqual(PASSES, executor.resets)

    def test_starting_runs_the_mode_own_enable_once(self):
        """The Start button sets `_enabled` directly, so the override that resets a run would never fire."""
        _, _, tasks = moved(ChaosMode)
        with self.assertRaises(TaskDisabledException):
            tasks[0].run()
        self.assertEqual(1, tasks[0].enables)

    def test_a_mode_that_stops_itself_ends_the_run_cleanly(self):
        """A round limit disables the task from inside run, which must not read as an abandoned task."""
        executor, _, tasks = moved(ChaosMode)
        task = tasks[0]
        task.stop_after = 2
        task.run()
        self.assertEqual(2, task.passes)
        self.assertEqual(1, executor.resets)

    def test_the_pace_is_measured_from_the_start_of_each_pass(self):
        """Sleeping the whole interval after the work would stretch every cycle by the length of the pass."""
        executor, _, tasks = moved(ChaosMode)
        with self.assertRaises(TaskDisabledException):
            tasks[0].run()
        # One sleep per pass, less the last: the stop lands before the loop gets that far.
        self.assertEqual(PASSES - 1, len(executor.sleeps))
        for slept in executor.sleeps:
            self.assertGreater(slept, 0)
            self.assertLessEqual(slept, 1)

    def test_the_pace_can_be_changed_while_the_mode_runs(self):
        """Capturing the interval once meant nothing could ever repace the loop.

        `src/en/observe.py` looks more often while a battle is on screen, because the game's own Auto AI
        plays several cards a second and a one second pace cannot see them one at a time.
        """
        executor, _, tasks = moved(ChaosMode)
        tasks[0].hurry_to = 0.25
        with self.assertRaises(TaskDisabledException):
            tasks[0].run()
        self.assertTrue(executor.sleeps)
        for slept in executor.sleeps:
            self.assertLessEqual(slept, 0.25)

    def test_a_mode_with_no_interval_does_not_sleep(self):
        executor, _, tasks = moved(ChaosMode, interval=0)
        with self.assertRaises(TaskDisabledException):
            tasks[0].run()
        self.assertEqual([], executor.sleeps)

    def test_pausing_records_itself_so_the_card_can_offer_resume(self):
        """`TaskCard` reads `task.paused`, which upstream's trigger branch never sets."""
        executor, _, tasks = moved(ChaosMode)
        task = tasks[0]
        task.pause()
        self.assertTrue(executor.paused)
        self.assertTrue(task._paused)

    def test_the_scaffold_tasks_are_no_longer_registered(self):
        """Configuration Demo Task and Diagnosis Performance Test are gone from the Tasks tab."""
        self.assertEqual([], config["onetime_tasks"])

    def test_the_demo_hotkey_setting_is_gone_from_the_settings_tab(self):
        names = [option.name for option in config["global_configs"]]
        self.assertNotIn("Game Hotkey Config", names)


class TestIdleDashboard(unittest.TestCase):
    """The Info table before any task has run, which upstream hides until the first run."""

    class Tab:
        """A task tab reduced to what the idle table reads and draws, with upstream's own methods as no-ops."""

        def __init__(self, tasks):
            self.tasks = tasks
            self.last_task = None
            self.drawn = None
            self.title = types.SimpleNamespace(text="", setText=lambda text: setattr(self.title, "text", text))
            self.task_info_container = types.SimpleNamespace(titleLabel=self.title)
            self.update_info_table = partial(dashboard.showing_while_idle(lambda tab: None), self)
            self.close_task_info = partial(dashboard.dismissing_while_idle(lambda tab: None), self)

        def update_task_info(self, task):
            self.drawn = dict(task.info)

    def test_idle_shows_the_static_rows_until_the_x_or_a_run(self):
        # Each step is a regression on its own: hidden at launch, the X ignored, or idle rows over a real run.
        tab = self.Tab([types.SimpleNamespace(config={"游戏语言": "English"})])
        tab.update_info_table()
        # As a list, because the team belongs above the two rows that never change rather than under them.
        self.assertEqual([(dashboard.COMBATANTS, dashboard.UNREAD), ("Game Language", "English"),
                          ("Version", "dev")], list(tab.drawn.items()))
        self.assertEqual(dashboard.IDLE, tab.title.text)

        tab.drawn = None
        tab.last_task = object()
        tab.update_info_table()
        self.assertIsNone(tab.drawn)

        tab = self.Tab([types.SimpleNamespace(config={})])
        tab.close_task_info()
        tab.update_info_table()
        self.assertIsNone(tab.drawn)


class TestRebuiltCardList(unittest.TestCase):
    """The card list the task tabs throw away and rebuild whenever the task list changes.

    Neither `ExpandLayout` nor ok-script's `ExpandCardLayout` shows the child it is handed, so a tab the user
    is looking at rebuilds into a blank page. `handle_chaos_reward_claim` asks for a rebuild the moment the
    loot cards run out, so this is a mid-run failure rather than a hypothetical one.
    """

    @classmethod
    def setUpClass(cls):
        # Offscreen has to be chosen before `QApplication` exists.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])
        cls.expand_card_layout = import_ui("widget.ExpandCardLayout", "ExpandCardLayout")
        assert cls.expand_card_layout is not None, "ok-script no longer provides ExpandCardLayout"
        # Applied with the escape hatch set, which also pins that the hatch cannot switch this patch off.
        with mock.patch.dict(os.environ, {layout.DISABLE_ENV: "1"}):
            layout.apply()

    def listed(self):
        """Build an empty card list.

        Returns:
            The `(view, layout)` pair, neither of them shown yet.
        """
        from PySide6.QtWidgets import QWidget

        view = QWidget()
        return view, self.expand_card_layout(view)

    def test_a_card_added_to_a_list_on_screen_is_drawn(self):
        from PySide6.QtWidgets import QWidget

        view, card_layout = self.listed()
        view.show()
        card = QWidget()
        card_layout.addWidget(card)
        self.assertTrue(card.isVisible(), "the rebuilt card is hidden, so the tab draws nothing")

    def test_a_card_added_before_the_list_is_up_still_waits_for_it(self):
        """Startup adds its cards to a hidden tab, and Qt's own show cascade is what draws those."""
        from PySide6.QtWidgets import QWidget

        view, card_layout = self.listed()
        card = QWidget()
        card_layout.addWidget(card)
        self.assertFalse(card.isVisible())
        view.show()
        self.assertTrue(card.isVisible())


if __name__ == "__main__":
    unittest.main()
