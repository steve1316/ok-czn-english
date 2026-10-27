"""Check that a run starting on the Combatants tab reads it instead of tapping its way back to it, and that Sortie goes there once a run."""

import sys
import types
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import navigation, rewards  # noqa: E402
from src.en.battle import PARTY  # noqa: E402

TARGET = "Arabella"
# What the log shows on the Combatants tab, at the three points upstream reads names from.
ON_THE_TAB = {(0.159, 0.368): "Arabella", (0.432, 0.368): "Veronica", (0.705, 0.369): "Mika"}
# A sibling tab: names at the same points, none of them a combatant.
ANOTHER_TAB = {(0.159, 0.368): "Whisper", (0.432, 0.368): "Ember", (0.705, 0.369): "Tallow"}
# The taps upstream's capture makes: the 3-person icon, the Combatants tab, then the one that closes the page.
CLOSE_PAGE = (0.960, 0.054)


class FakeTask:
    """A mode recording the taps a handler asks for."""

    def __init__(self):
        self.clicks = []
        self.boxes = []

    def click_box(self, box, *args, **kwargs):
        self.boxes.append(getattr(box, "name", box))


def install(names, target=TARGET):
    """Put stand-in task modules where `handlers.loaded` will find them.

    Args:
        names: What OCR reads at each of the three name points.
        target: The combatant the run is farming, as the setting would give it.

    Returns:
        The stand-in `utils_chaos`, whose `_move_and_click` the capture calls.
    """
    utils = types.ModuleType("utils")
    utils.find_box_at_point = lambda task, x, y: (
        types.SimpleNamespace(name=names[(x, y)]) if (x, y) in names else None
    )
    utils._get_config_value = lambda task, key, default=None: target

    utils_chaos = types.ModuleType("utils_chaos")
    utils_chaos._move_and_click = lambda task, x, y: task.clicks.append((x, y))

    sys.modules["utils"] = utils
    sys.modules["utils_chaos"] = utils_chaos
    return utils_chaos


def upstream_capture(utils_chaos, extra_boxes=0):
    """Stand in for upstream's capture: the two navigation taps, then the tap that closes the page.

    Args:
        utils_chaos: The module whose `_move_and_click` the capture reaches for.
        extra_boxes: Box clicks beyond the one upstream makes today, for the rebase the tally guards against.

    Returns:
        A handler that records what it tapped and reports that it handled the frame.
    """
    def handle_archive_target_member(task):
        for _ in range(1 + extra_boxes):
            task.click_box(types.SimpleNamespace(name="memberinfo"))
        utils_chaos._move_and_click(task, *navigation.COMBATANTS_TAB)
        utils_chaos._move_and_click(task, *CLOSE_PAGE)
        return True

    return handle_archive_target_member


class TestOnCombatantsTab(unittest.TestCase):
    """The guard that decides whether the trip can be skipped."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def test_a_combatant_on_screen_proves_the_tab_is_open(self):
        install(ON_THE_TAB)
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_sibling_tab_is_not_mistaken_for_it(self):
        """Partners and Fate draw names at the same points, so names alone would not be proof."""
        install(ANOTHER_TAB)
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))

    def test_a_screen_with_no_names_is_not_it(self):
        install({})
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))

    def test_one_readable_slot_is_enough(self):
        install({(0.705, 0.369): TARGET})
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_name_read_with_extra_text_still_counts(self):
        """Upstream matches either way round, so anything its own read would accept has to be accepted here."""
        install({(0.159, 0.368): "Arabella Lv40"})
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_it_does_not_depend_on_who_is_farmed(self):
        # A run farming nobody clicked the icon and the tab every time, because the farmed name was the only proof.
        for target in ("", "(none)", "Heidemarie"):
            with self.subTest(target=target):
                install(ON_THE_TAB, target=target)
                self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_short_name_inside_a_longer_word_does_not_count(self):
        install({(0.159, 0.368): "Fenia"})
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))


class TestReadingInPlace(unittest.TestCase):
    """The wrapper drops the two navigation taps and leaves everything else upstream does alone."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def capture(self, names, extra_boxes=0):
        """Run the wrapped capture against a screen.

        Args:
            names: What OCR reads at the three name points.
            extra_boxes: Box clicks beyond the one upstream makes today.

        Returns:
            A `(task, handled)` pair.
        """
        utils_chaos = install(names)
        task = FakeTask()
        handled = navigation.reading_in_place(upstream_capture(utils_chaos, extra_boxes))(task)
        return task, handled

    def test_only_the_trip_back_to_the_screen_is_dropped(self):
        """Both navigation taps go, the tap that closes the page stays, and the answer is handed back."""
        task, handled = self.capture(ON_THE_TAB)
        self.assertEqual([], task.boxes)
        self.assertEqual([CLOSE_PAGE], task.clicks)
        self.assertTrue(handled)

    def test_a_run_starting_elsewhere_taps_only_the_icon(self):
        """The 3-person icon already lands on the Combatants tab, so the tab tap after it would do nothing."""
        task, handled = self.capture(ANOTHER_TAB)
        self.assertEqual(["memberinfo"], task.boxes)
        self.assertEqual([CLOSE_PAGE], task.clicks)
        self.assertTrue(handled)

    def test_a_capture_that_throws_still_puts_them_back(self):
        """A capture that raised while the taps were stood in for would leave upstream permanently rewired."""
        utils_chaos = install(ON_THE_TAB)
        original = utils_chaos._move_and_click
        task = FakeTask()

        def raising(task):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            navigation.reading_in_place(raising)(task)
        self.assertIs(original, utils_chaos._move_and_click)
        self.assertNotIn("click_box", task.__dict__)

    def test_the_stand_in_keeps_the_name_upstream_logs(self):
        """`_move_and_click` logs the name of the frame that called it, and this stands in mid-capture."""
        stand_in = navigation.without_the_tab_tap(lambda task, x, y: None, navigation.Dropped())
        self.assertEqual("handle_archive_target_member", stand_in.__code__.co_name)


class TestTheTallyNoticesARebase(unittest.TestCase):
    """Both taps are recognised by shape, so upstream moving one has to be made loud rather than silent."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def warnings(self, extra_boxes=0, tab=navigation.COMBATANTS_TAB):
        """Run the wrapped capture and collect what it warned about.

        Args:
            extra_boxes: Box clicks beyond the one upstream makes today.
            tab: Where the capture taps for the Combatants tab.

        Returns:
            The warning lines the wrapper logged.
        """
        utils_chaos = install(ON_THE_TAB)
        said = []
        original_warning = navigation.logger.warning
        navigation.logger.warning = lambda message, *args, **kwargs: said.append(message)
        try:
            def handle_archive_target_member(task):
                for _ in range(1 + extra_boxes):
                    task.click_box(types.SimpleNamespace(name="memberinfo"))
                utils_chaos._move_and_click(task, *tab)
                return True

            navigation.reading_in_place(handle_archive_target_member)(FakeTask())
        finally:
            navigation.logger.warning = original_warning
        return said

    def test_the_shape_upstream_has_today_says_nothing(self):
        self.assertEqual([], self.warnings())

    def test_a_frame_upstream_declines_says_nothing(self):
        """Off the page upstream returns before tapping, and a live run logged the warning on every such frame."""
        install(ANOTHER_TAB)
        said = []
        original_warning = navigation.logger.warning
        navigation.logger.warning = lambda message, *args, **kwargs: said.append(message)
        try:
            navigation.reading_in_place(lambda task: False)(FakeTask())
        finally:
            navigation.logger.warning = original_warning
        self.assertEqual([], said)

    def test_a_moved_tab_tap_is_reported(self):
        """The skip would quietly stop saving anything, which is the failure nobody would notice."""
        said = self.warnings(tab=(0.250, 0.056))
        self.assertEqual(1, len(said))
        self.assertIn("dropped 0 and 1", said[0])

    def test_a_second_box_click_is_reported(self):
        """This is the sharper one: a tap upstream needed would have been swallowed."""
        said = self.warnings(extra_boxes=1)
        self.assertEqual(1, len(said))
        self.assertIn("dropped 1 and 2", said[0])


class TestSortieTeamTrip(unittest.TestCase):
    """Sortie taps through to the team once a run, and the new run's roster replaces the old party."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def test_each_run_taps_through_once_and_reads_its_own_party(self):
        install(ON_THE_TAB)
        utils = sys.modules["utils"]
        on_map = [False]
        utils._get_current_hp_percent = lambda task: 100 if on_map[0] else False
        utils._move_and_click = lambda task, x, y: task.clicks.append((x, y))
        task = FakeTask()
        task.sleep = lambda seconds: None
        task.info_set = lambda key, value: None
        task.node_status = {}
        clock = [0.0]

        with mock.patch.object(navigation.time, "monotonic", lambda: clock[0]):
            self.assertFalse(navigation.handle_open_team(task), "off the map there is nothing to tap")
            on_map[0] = True
            self.assertTrue(navigation.handle_open_team(task))
            # A pending dialog swallowed the tap, and its own handler needs the next frames to clear it.
            self.assertFalse(navigation.handle_open_team(task))
            # Once it has, the team is tapped for again, but not past `TEAM_TRIES`.
            for _ in range(navigation.TEAM_TRIES - 1):
                clock[0] += navigation.TEAM_RETRY_SECONDS
                self.assertTrue(navigation.handle_open_team(task))
            clock[0] += navigation.TEAM_RETRY_SECONDS
            self.assertFalse(navigation.handle_open_team(task))
            self.assertEqual([navigation.TEAM_PORTRAITS] * navigation.TEAM_TRIES, task.clicks)
            task.clicks.clear()

            # Upstream rebuilds `node_status` for the next run, and the last run's party must not outlive it.
            task.node_status = {}
            setattr(task, PARTY, frozenset({"Yuki"}))
            self.assertTrue(navigation.handle_open_team(task))
            self.assertEqual(frozenset(), getattr(task, PARTY))
            self.assertEqual([navigation.TEAM_PORTRAITS], task.clicks)

            rewards.remember_team(task, utils)
            self.assertEqual({"Arabella", "Veronica", "Mika"}, getattr(task, PARTY))
            clock[0] += navigation.TEAM_RETRY_SECONDS
            self.assertFalse(navigation.handle_open_team(task), "a team read stops the retries")


if __name__ == "__main__":
    unittest.main()
