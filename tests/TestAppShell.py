"""Check that the game modes run from a Start button, that the scaffold tabs are gone, and that the list draws."""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ok.task.exceptions import TaskDisabledException  # noqa: E402
from ok.util.config import Config  # noqa: E402

from src import config as src_config  # noqa: E402
from src.config import config  # noqa: E402
from src.en import devices, monitors, shell, shutdown, task_list  # noqa: E402
from src.en.framework import import_ui  # noqa: E402
from tests.fakes import EchoApp  # noqa: E402

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

    def test_the_modes_move_to_the_list_that_has_start_buttons(self):
        """`TaskRow` draws a switch for anything left in the trigger list, and buttons for this one."""
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

    def test_the_script_and_template_pages_are_turned_off(self):
        _, task_manager, _ = moved(ChaosMode)
        self.assertFalse(task_manager.has_custom)

    def test_the_edit_button_is_dropped_with_the_page_it_opens(self):
        """`TaskDetail` shows it from `is_custom`, and it opens a Script page that no longer exists."""
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

    def test_pausing_records_itself_so_the_page_can_offer_resume(self):
        """The Tasks page reads `task.paused`, which upstream's trigger branch never sets."""
        executor, _, tasks = moved(ChaosMode)
        task = tasks[0]
        task.pause()
        self.assertTrue(executor.paused)
        self.assertTrue(task._paused)

    def test_the_scaffold_tasks_are_no_longer_registered(self):
        """Configuration Demo Task and Diagnosis Performance Test are gone from the Tasks page."""
        self.assertEqual([], config["onetime_tasks"])

    def test_the_demo_hotkey_setting_is_gone_from_the_settings_page(self):
        names = [option.name for option in config["global_configs"]]
        self.assertNotIn("Game Hotkey Config", names)

    def test_a_fresh_install_sends_keys_by_post_message(self):
        # The first method is the default, and Genshin sends every key as A, so no card or Ego hotkey ever lands.
        self.assertEqual("PostMessage", config["windows"]["interaction"][0])

    def test_auto_ocr_never_picks_openvino(self):
        # OpenVINO crashed the app at startup on an Intel machine, so it must stay opt-in.
        with mock.patch.object(src_config, "_read_ocr_backend", return_value=src_config.OCR_BACKEND_AUTO), \
                mock.patch.object(src_config, "_openvino_is_available", return_value=True), \
                mock.patch.dict(os.environ, {"PROCESSOR_IDENTIFIER": "GenuineIntel"}):
            self.assertFalse(src_config.resolve_use_openvino())


class TestTasksPage(unittest.TestCase):
    """The patches on the real Tasks page, whose rows and pane a stand-in could not catch being renamed."""

    @classmethod
    def setUpClass(cls):
        # Offscreen has to be chosen before `QApplication` exists.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])
        task_list.apply()
        cls.tasks_page = import_ui("tasks", "tasks_page")
        cls.task_row = import_ui("tasks.tasks_page", "TaskRow")
        cls.task_detail = import_ui("tasks.tasks_page", "TaskDetail")
        cls.folder = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def mode(self, executor, name, enabled):
        """Build a mode carrying what the page draws.

        Args:
            executor: The executor whose one-time list holds it.
            name: The mode's name.
            enabled: Whether it is running.

        Returns:
            The mode.
        """
        task = FakeTask(executor)
        task.name, task._enabled = name, enabled
        task.description, task.instructions, task.first_run_alert = "", "", None
        task.icon, task.group_name, task.is_custom = None, None, False
        task.running, task.paused, task.start_time = enabled, False, 0
        task.show_create_shortcut = False
        task.info = {}
        task.default_config = {"count": 1}
        task.config = Config(name, task.default_config, folder=self.folder.name)
        task.config_description, task.config_type = {}, {}
        return task

    def test_the_other_starts_lock_until_the_run_stops(self):
        # Locking alone is half of it. A Start that stays disabled after the run would strand every other mode.
        from ok import og

        executor = FakeExecutor()
        running, other = self.mode(executor, "Auto Sortie Mode", True), self.mode(executor, "Auto Chaos Mode", False)
        executor.onetime_tasks = [running, other]
        executor.waiting_for_task = lambda task: None
        with mock.patch.object(og, "executor", executor, create=True), mock.patch.object(og, "app", EchoApp(), create=True), \
                mock.patch.object(self.task_row, "refresh", shell.locking_row(self.task_row.refresh)), \
                mock.patch.object(self.task_detail, "refresh", shell.locking_detail(self.task_detail.refresh)):
            row = self.task_row(other, False)
            detail = self.task_detail()
            detail.show_task(other, False)
            for name, button in (("row", row.action_button), ("pane", detail.run_button)):
                with self.subTest(name):
                    self.assertEqual((False, "Stop Auto Sortie Mode first"), (button.isEnabled(), button.toolTip()))
            running._enabled = False
            row.refresh()
            detail.refresh()
            for name, button in (("row", row.action_button), ("pane", detail.run_button)):
                with self.subTest(name):
                    self.assertTrue(button.isEnabled())
                    self.assertNotIn("first", button.toolTip())

    def test_every_mode_draws_its_icon_in_the_themes_ink(self):
        # Through the page's own tile: a renamed mode class or an icon the framework stops accepting falls back to a monogram in silence.
        from ok.ui.qt.kit.theme import Theme, theme

        self.addCleanup(theme.set_theme, theme.mode)
        for name in task_list.ICON_FILES:
            self.assertIn(f"class {name}(", (REPO_ROOT / "ok_tasks" / f"{name}.py").read_text(encoding="utf-8"))
            task = type(name, (), {"name": name})()
            task_list.set_mode_icon(task)
            tile = self.tasks_page.TaskIconTile(task)
            for mode in (Theme.DARK, Theme.LIGHT):
                with self.subTest(name=name, mode=mode):
                    theme.set_theme(mode)
                    image = tile.pixmap().toImage()
                    pixels = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())]
                    # Thin lines stay anti-aliased at this size, so the strongest pixel only comes close to the ink.
                    strongest, ink = max(pixels, key=lambda pixel: pixel.alpha()), theme.color("text")
                    self.assertGreater(strongest.alpha(), 100)
                    self.assertLess(max(abs(strongest.red() - ink.red()), abs(strongest.green() - ink.green()), abs(strongest.blue() - ink.blue())), 24)

    def test_the_list_is_a_narrow_column_of_names_under_modes(self):
        # Each of these is a name the page reads at build time, so a framework rename puts the stock wide list back without an error.
        from ok import og

        executor = FakeExecutor()
        task = self.mode(executor, "Chaos", False)
        task.description = "Plays whole runs."
        executor.onetime_tasks = [task]
        with mock.patch.object(og, "executor", executor, create=True), mock.patch.object(og, "app", EchoApp(), create=True), \
                mock.patch.object(Config, "config_folder", self.folder.name):
            page = self.tasks_page.TasksPage()
            row = self.task_row(task, False)
        row.resize(300, 58)
        self.assertEqual("Modes", page.onetime_section.title_label.text())
        self.assertEqual(task_list.LIST_WIDTH, page.onetime_section.parentWidget().width())
        self.assertEqual((True, ""), (row.description_label.isHidden(), row.description_label.text()))


class TestEmulatorConnect(unittest.TestCase):
    """Refresh dials an emulator only once something is listening on its port."""

    CASES = (
        ("a closed emulator is listed without dialling it", "127.0.0.1:5555", True, {5037}, False),
        ("a running emulator is still dialled", "127.0.0.1:16384", True, {5037, 16384}, True),
        ("a phone on the network is always dialled", "192.168.0.20:5555", True, set(), True),
        ("a caller that asked not to dial is left alone", "127.0.0.1:5555", False, {5555}, False),
        ("an unreadable port table falls back to dialling", "127.0.0.1:5555", True, None, True),
    )

    def test_only_a_listening_emulator_is_dialled(self):
        for why, addr, asked, listening, dialled in self.CASES:
            with self.subTest(why):
                calls = []
                connect = devices.dialling_only_listening(lambda manager, a, try_connect=True: calls.append((a, try_connect)),
                                                          lambda: listening)
                connect(object(), addr, asked)
                self.assertEqual([(addr, dialled)], calls)

    def test_running_emulators_are_found_by_name_and_reported_by_path(self):
        processes = [types.SimpleNamespace(info={"name": "HD-Player.exe"}, exe=lambda: "C:/BlueStacks_nxt/HD-Player.exe"),
                     types.SimpleNamespace(info={"name": "chrome.exe"}, exe=lambda: self.fail("a non-emulator's path was read"))]
        self.assertEqual(["C:/BlueStacks_nxt/HD-Player.exe"], list(devices.emulator_exes(processes)))


class TestMonitorLeftOfTheMain(unittest.TestCase):
    """The framework skips geometry at a negative position unless the game is in front, taking it for a minimized window."""

    # What `get_window_bounds` returned for the game on the monitor left of the main one.
    LEFT_MONITOR = (-1938, 135, 1936, 1119, 1920, 1080, 1.0)

    def window(self, **fields):
        """Build the framework's window record as it stood after its own update.

        Args:
            fields: Fields to set over a record the framework never filled in.

        Returns:
            The record.
        """
        record = dict(x=0, y=0, window_width=0, window_height=0, client_width=0, client_height=0, width=0, height=0,
                      scaling=1.0, visible=False, frame_aspect_ratio=0)
        record.update(fields)
        return types.SimpleNamespace(**record)

    def test_a_window_left_of_the_main_monitor_gets_its_geometry(self):
        window = self.window()
        self.assertTrue(monitors.take_geometry(window, self.LEFT_MONITOR, minimized=False))
        self.assertEqual((-1938, 135, 1936, 1119, 1920, 1080),
                         (window.x, window.y, window.window_width, window.window_height, window.width, window.height))

    def test_a_minimized_window_is_still_skipped(self):
        window = self.window()
        self.assertFalse(monitors.take_geometry(window, (-32000, -32000, 160, 28, 0, 0, 1.0), minimized=True))
        self.assertEqual(0, window.window_width)

    def test_the_frame_is_cropped_to_the_game_ratio_as_the_framework_does(self):
        window = self.window(frame_aspect_ratio=16 / 9)
        monitors.take_geometry(window, (-1938, 135, 1936, 1239, 1920, 1200, 1.0), minimized=False)
        self.assertEqual((1920, 1080, 1200), (window.width, window.height, window.client_height))


class TestWindowCanBeReached(unittest.TestCase):
    """The framework keeps the main window on a screen, which is why this fork carries no patch for it."""

    @classmethod
    def setUpClass(cls):
        # Offscreen has to be chosen before `QApplication` exists.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])

    def test_the_window_opens_on_a_screen(self):
        # A framework bump that drops this strands a window saved on an unplugged monitor, with no way to drag it back.
        from PySide6.QtWidgets import QWidget

        cases = (
            ("saved on an unplugged monitor", (3000, 300, 700, 500), (700, 500)),
            ("nothing saved and a default taller than the screen", (-1, -1, -1, -1), (1000, 1000)),
        )
        for name, saved, default in cases:
            with self.subTest(name):
                class Window(QWidget):
                    ok_config = dict(zip(("window_x", "window_y", "window_width", "window_height"), saved), window_maximized=False)
                    set_window_size = import_ui("MainWindow", "MainWindow").set_window_size

                    def apply_navigation_state(self):
                        pass

                window = Window()
                window.set_window_size(*default, 100, 100)
                self.assertTrue(window.screen().availableGeometry().contains(window.geometry()))


class TestExitStopsAdb(unittest.TestCase):
    """The adb server upstream leaves running, which made the Launcher think the app never closed."""

    class Proc:
        """A running process reduced to what the exit hook reads and kills."""

        def __init__(self, name, exe):
            self.pid = id(self)
            self.info = {"name": name, "exe": exe}
            self.killed = False

        def kill(self):
            self.killed = True

    def test_only_the_bundled_adb_is_stopped(self):
        # Real adbutils, so a rename of the bundled binary's folder helper fails here rather than silently at exit.
        from adbutils._utils import _get_bin_dir

        ours = self.Proc("adb.exe", os.path.join(_get_bin_dir(), "adb.exe"))
        theirs = self.Proc("adb.exe", r"C:\Android\platform-tools\adb.exe")
        with mock.patch("psutil.process_iter", return_value=[ours, theirs]):
            shutdown.stop_bundled_adb()
        self.assertTrue(ours.killed)
        self.assertFalse(theirs.killed)


if __name__ == "__main__":
    unittest.main()
