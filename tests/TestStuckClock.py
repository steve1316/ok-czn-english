"""Check that a new run starts fresh: its own stuck clock, and free to take the first rest area it reaches.

Upstream decides a screen has frozen by keeping two things on the task, and the task outlives the run - the
Start button re-enables the same object. Nothing cleared them between runs, so the clock kept counting through
however long the app sat stopped, and the first frame of a new run could report a minute of frozen screen.

These run upstream's own detector rather than a stand-in for it, because the bug is in what it remembers.
"""

import importlib
import sys
import time
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402
import utils_chaos  # noqa: E402
import utils_sortie  # noqa: E402

from src.en import meditation, notify, obtain, rest, stuck  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

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


class TestRestFlag(unittest.TestCase):
    """A Chaos run started inside an event walked past the rest area after it, because the flag starts off."""

    @classmethod
    def setUpClass(cls):
        rest.install(utils)

    def test_every_upstream_reset_leaves_the_next_rest_area_usable(self):
        # Against upstream's own resets, so one that stops building its status through the wrapped builder fails here.
        for reset in (utils.reset_all_status, utils.reset_mission_status, utils.reset_layer_status):
            with self.subTest(reset=reset.__name__):
                task = SimpleNamespace(node_status={rest.FLAG: False}, config={}, default_config={})
                reset(task)
                self.assertIs(True, task.node_status[rest.FLAG])

    def test_a_run_started_at_a_safe_zone_enters_the_shop_when_set_to(self):
        # A run started on a safe zone's screen walked out past the open Dellang shop, because only the route
        # screen ever turned the shop on.
        for setting in (True, False):
            with self.subTest(setting=setting):
                task = SimpleNamespace(node_status={}, config={rest.SHOP_SETTING: setting}, default_config={})
                utils.reset_all_status(task)
                seen = []
                handler = rest.deciding_the_shop(lambda task_: seen.append(task_.node_status[rest.SHOP]), utils)
                handler(task)
                self.assertEqual([setting], seen)

    def test_a_shop_already_spent_is_not_reopened(self):
        task = SimpleNamespace(node_status={rest.SHOP: False}, config={rest.SHOP_SETTING: True}, default_config={})
        rest.deciding_the_shop(lambda task_: None, utils)(task)
        self.assertIs(False, task.node_status[rest.SHOP])

    def test_every_handler_reading_the_shop_still_exists_upstream(self):
        # `wrap` skips a name it cannot find, so an upstream rename would otherwise drop the fix silently.
        for module_name, handler_name in rest.READS_SHOP:
            with self.subTest(handler=handler_name):
                self.assertTrue(callable(getattr(importlib.import_module(module_name), handler_name, None)))


class TestOfferedInteraction(unittest.TestCase):
    """The safe zone the run walked past because only the route screen re-arms upstream's flag.

    Upstream spends `flash_or_rest` on the first rest area and re-arms it on the route selection screen. A
    stretch of a run that never shows that screen leaves it off, so every later safe zone is skipped - measured
    at three in a row, each reading the rest feature at over 96%, while the game still offered an interaction.
    The game prints the count on screen, so that is what decides now.
    """

    # The line OCR returned on the capture, at 0.981 confidence, and the rest of that screen with it - a
    # regex loose enough to answer off one of the others would skip the area just as quietly.
    OFFERED = "Available Safe Zone Interactions: 1"
    SPENT = "Available Safe Zone Interactions: 0"
    OTHER_TEXT = ("Rest", "Free", "Dellang Shop", "Meditation", "80",
                  "The number of uses will not be deducted when Using shops.", "Skip")

    def task_seeing(self, caption, flag=False):
        """Build a task on a safe zone screen.

        Args:
            caption: The counter line as OCR read it, or None for a screen where it was not found.
            flag: What upstream's flag is set to before the handler runs.

        Returns:
            A task carrying that screen's boxes and flag.
        """
        texts = [FakeBox(name, 0.5, 0.5) for name in self.OTHER_TEXT]
        if caption is not None:
            texts.append(FakeBox(caption, 0.842, 0.771))
        return SimpleNamespace(node_status={rest.FLAG: flag}, all_texts=texts)

    def watching(self):
        """Build a handler that records the flag it was given.

        Returns:
            A `(handler, seen)` pair, where `seen` collects one entry per call.
        """
        seen = []
        return (lambda task: seen.append(task.node_status[rest.FLAG])), seen

    def test_the_count_is_read_off_the_screen(self):
        # The last is how a live run read the "1", which skipped the safe zone.
        for caption, expected in ((self.OFFERED, 1), (self.SPENT, 0), (None, None), ("Available Safe Zone Interactions:'", 1)):
            with self.subTest(caption=caption):
                self.assertEqual(expected, rest.interactions_left(self.task_seeing(caption)))

    def test_an_offered_interaction_lets_the_handler_rest(self):
        handler, seen = self.watching()
        rest.taking_the_offered_interaction(handler)(self.task_seeing(self.OFFERED))
        self.assertEqual([True], seen, "the handler still saw the stale flag, so it skips the safe zone")

    def test_upstreams_own_answer_stands_everywhere_else(self):
        # Nothing to override: the area is spent, the screen is not a safe zone, or the flag is already on.
        for caption, flag in ((self.SPENT, False), (None, False), (self.OFFERED, True)):
            with self.subTest(caption=caption, flag=flag):
                handler, seen = self.watching()
                rest.taking_the_offered_interaction(handler)(self.task_seeing(caption, flag=flag))
                self.assertEqual([flag], seen)

    def test_the_override_never_outlasts_the_call(self):
        """However the handler ends, the run's own flag is what the next frame reads."""
        def rests(task):
            task.node_status[rest.FLAG] = False
            return True

        def explodes(task):
            raise RuntimeError("boom")

        for why, handler in (("rested", rests), ("declined", lambda task: False), ("raised", explodes)):
            with self.subTest(why):
                task = self.task_seeing(self.OFFERED)
                try:
                    rest.taking_the_offered_interaction(handler)(task)
                except RuntimeError:
                    pass
                self.assertIs(False, task.node_status[rest.FLAG])

    def test_leaving_unused_is_cancelled_and_the_area_used(self):
        # The run's leave warning as OCR read it. Upstream's centre Confirm would walk out with the interaction unspent.
        cancel, clicked = FakeBox("取消", 0.347, 0.632), []
        task = SimpleNamespace(width=1920, height=1080, node_status={rest.FLAG: False}, log_info=lambda message: None, sleep=lambda seconds: None,
                               click_box=clicked.append, all_texts=[FakeBox("You have not yet used a Safe Zone interaction.", 0.5, 0.45),
                                                                    FakeBox("Do you really wish to leave?", 0.5, 0.5), cancel, FakeBox("确认", 0.653, 0.632)])
        self.assertTrue(rest.handle_unused_warning(task))
        self.assertEqual([cancel], clicked)
        self.assertIs(True, task.node_status[rest.FLAG])


class TestQuickObtain(unittest.TestCase):
    """Each Obtain tap sat through two seconds of waiting before the next reward could be claimed."""

    def test_upstreams_obtain_tap_waits_no_longer_than_settle(self):
        # Upstream's own handler, so a rename or a wait that stops going through `task.sleep` fails here.
        waits, clicks = [], []
        task = SimpleNamespace(width=1920, height=1080, all_texts=[FakeBox("获得", 0.924, 0.922)], log_info=lambda message: None)
        task.sleep = waits.append

        def click_box(box, after_sleep=1):
            # ok-script's click waits through `task.sleep`, so the stand-in has to reach it the same way.
            clicks.append(box.name)
            task.sleep(after_sleep)

        task.click_box = click_box
        self.assertTrue(obtain.quick(utils.handle_obtain_reward)(task))
        self.assertEqual(["获得"], clicks)
        self.assertTrue(waits)
        self.assertLessEqual(max(waits), obtain.SETTLE)


class TestSortieFreeEpiphany(unittest.TestCase):
    """Sortie's rest handler never looked for the icon, so its camps walked past a free Epiphany."""

    OFFERED = "Available Safe Zone Interactions: 1"
    SPENT = "Available Safe Zone Interactions: 0"
    ICON = FakeBox("special_flash_luosi", 0.343, 0.5)

    @classmethod
    def setUpClass(cls):
        rest.install(utils)

    def seeing(self, icon, line=OFFERED):
        """Build a task whose icon search finds the given box.

        Args:
            icon: What `find_one` returns, or None.
            line: The safe zone line on screen, or None.

        Returns:
            A `(task, searched, clicked)` trio, where the two lists collect each search and click.
        """
        searched, clicked = [], []
        task = SimpleNamespace(
            width=1920, height=1080, all_texts=[FakeBox(line, 0.842, 0.771)] if line else [], log_info=lambda message: None,
            sleep=lambda seconds: None, move_relative=lambda x, y: None, click=lambda x, y: clicked.append((x, y)),
            box_of_screen=lambda *region: region, find_one=lambda feature_name, box: searched.append((feature_name, box)) or icon)
        return task, searched, clicked

    def test_it_runs_just_ahead_of_sorties_rest_handler_and_only_there(self):
        # Off the list, the handler would be correct and never run.
        names = [handler.__name__ for handler in utils_sortie.PAGE_HANDLERS]
        self.assertEqual(names.index("handle_rest_sortie") - 1, names.index("handle_free_epiphany"))
        self.assertNotIn("handle_free_epiphany", [handler.__name__ for handler in utils_chaos.PAGE_HANDLERS])

    def test_sortie_takes_the_icon_exactly_as_chaos_does(self):
        # Against the real Chaos handler, so upstream's search moving away from the copy in `rest.py` fails here.
        chaos, chaos_searched, chaos_clicked = self.seeing(self.ICON)
        sortie, sortie_searched, sortie_clicked = self.seeing(self.ICON)
        self.assertIs(True, utils.handle_rest(chaos))
        self.assertIs(True, rest.free_epiphany_handler(utils)(sortie))
        self.assertEqual(chaos_searched, sortie_searched)
        self.assertEqual(chaos_clicked, sortie_clicked)
        self.assertEqual(1, len(sortie_clicked))

    def test_the_search_runs_only_at_a_safe_zone_and_a_miss_falls_through(self):
        # A count of 0 still searches, since the line is there to say this is a safe zone.
        for line, searches in ((None, 0), (self.OFFERED, 1), (self.SPENT, 1)):
            with self.subTest(line=line):
                task, searched, _ = self.seeing(None, line)
                self.assertFalse(rest.free_epiphany_handler(utils)(task))
                self.assertEqual(searches, len(searched))


def party_bar(stress):
    """Paint the party's Stress bars onto a black 1080p frame, the purple fill over the grey track as the client draws them.

    Args:
        stress: One share from 0 to 1 per combatant.

    Returns:
        A BGR frame.
    """
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for (left, top, right, bottom), level in zip(meditation.STRESS_BARS, stress):
        x1, x2, y1, y2 = int(left * 1920) + 10, int(right * 1920) - 10, int(top * 1080), int(bottom * 1080) + 1
        frame[y1:y2, x1:x2] = (77, 72, 70)
        frame[y1:y2, x1:x1 + int((x2 - x1) * level)] = (240, 60, 200)
    return frame


class TestMeditation(unittest.TestCase):
    """Meditation re-rolls the Epiphany on a pinned card, and only when the party could spare the Rest."""

    OFFERED = "Available Safe Zone Interactions: 1"
    ICON = FakeBox("meditate", 0.878, 0.607)

    @classmethod
    def setUpClass(cls):
        meditation.install(utils)

    def safe_zone(self, hp="1796/1796", stress=(0.1, 0.2, 0.1), credits="287", switch=True):
        """Build a task on the Safe Zone screen, laid out as the Global client draws it.

        Args:
            hp: The party HP as OCR reads it.
            stress: Each combatant's Stress, painted into the frame.
            credits: The run's Credits as OCR reads them.
            switch: What `MEDITATE` is set to.

        Returns:
            A `(task, clicked)` pair, where `clicked` collects every box clicked.
        """
        clicked = []
        texts = [FakeBox(self.OFFERED, 0.842, 0.771), FakeBox(hp, 0.209, 0.040), FakeBox(credits, 0.734, 0.053),
                 FakeBox("Meditation", 0.804, 0.580), FakeBox("80", 0.835, 0.625), FakeBox("Rest", 0.327, 0.766)]
        task = SimpleNamespace(width=1920, height=1080, all_texts=texts, frame=party_bar(stress), config={meditation.MEDITATE: switch},
                               default_config={}, log_info=lambda message: None, sleep=lambda seconds: None, click_box=clicked.append,
                               box_of_screen=lambda *region: region, wait_ocr=lambda *args, **kwargs: None,
                               find_one=lambda feature_name, box: self.ICON if feature_name == meditation.MEDITATE_ICON else None)
        return task, clicked

    def test_a_healthy_calm_party_meditates_and_anything_less_rests(self):
        # Against upstream's own HP, Credit and config readers, so a rename there fails here rather than resting every time.
        for why, kwargs, meditates in (("fit", {}, True), ("hurt", {"hp": "1437/1796"}, False), ("stressed", {"stress": (0.1, 0.3, 0.1)}, False),
                                       ("poor", {"credits": "79"}, False), ("switched off", {"switch": False}, False)):
            with self.subTest(why):
                task, clicked = self.safe_zone(**kwargs)
                self.assertIs(meditates, meditation.safe_zone_handler(utils)(task))
                self.assertEqual([self.ICON] if meditates else [], clicked)

    def test_upstreams_own_list_never_sends_the_run_to_meditate(self):
        # The list and the threshold are gone from the settings. `utils_chaos` holds upstream's unwrapped handler, which shows the
        # screen does reach its Meditation click, so the wrapped one staying off it is the wrapper's doing.
        for handler, meditates in ((utils_chaos.handle_rest, True), (utils.handle_rest, False)):
            with self.subTest(wrapped=handler is utils.handle_rest):
                task, clicked = self.safe_zone()
                task.node_status = {rest.FLAG: True}
                task.member_status = {"deck": {"冥想": {"Hunting Instincts": True}}}
                task.config = {"多少信用点以上冥想": 0}
                handler(task)
                self.assertEqual(meditates, self.ICON in clicked)

    def card_screen(self, pinned, again_active):
        """Build a task on the card screen Meditation opens, one card on it.

        Args:
            pinned: Whether the card carries the build preset's pin.
            again_active: Whether "Epiphany Again" is lit, meaning a card is already chosen.

        Returns:
            A `(task, tapped, stand_ins)` trio: the task, every box or point tapped, and the upstream helpers to patch into `utils`.
        """
        tapped = []
        again, cancel = FakeBox("重新闪光", 0.9, 0.93, width=300), FakeBox("取消", 0.72, 0.93)
        task = SimpleNamespace(width=1920, height=1080, all_texts=[FakeBox("冥想重构卡牌", 0.27, 0.05, width=700), again, cancel],
                               log_info=lambda message: None, sleep=lambda seconds: None, click_box=tapped.append)
        stand_ins = dict(
            is_button_active=lambda task_, box: again_active,
            recognize_cards_in_deck=lambda task_, page="": [{"name": "Hunting Instincts", "x": 0.355, "y": 0.3, "pinned": pinned}],
            region_white_ratio=lambda task_, region: 0.0, _point_is_white=lambda *args: True, _scroll_card_page=lambda *args: tapped.append("scroll"),
            _move_and_click=lambda task_, x, y: tapped.append((x, y)))
        return task, tapped, stand_ins

    def test_a_pinned_card_is_taken_and_none_backs_out_to_rest(self):
        # Patched onto the real `utils`, so a rename upstream fails here. A chosen card is left to upstream's Epiphany Again, since
        # tapping it again would only un-choose it.
        for why, pinned, again_active, claimed, expected, meditating in (
                ("pinned", True, False, True, [(0.355, 0.3)], None), ("none pinned", False, False, True, ["取消"], False),
                ("already chosen", True, True, False, [], None)):
            with self.subTest(why):
                task, tapped, stand_ins = self.card_screen(pinned, again_active)
                with mock.patch.multiple(utils, **stand_ins):
                    self.assertIs(claimed, meditation.pick_handler(utils)(task))
                self.assertEqual(expected, [getattr(item, "name", item) for item in tapped])
                self.assertIs(meditating, meditation.decision(task))

    def test_the_popup_is_confirmed_only_while_the_fork_is_meditating(self):
        # Upstream's centre Confirm would otherwise walk straight back into the card screen just cancelled.
        for why, decided, expected in (("chosen", True, "确认"), ("turned down", False, "取消"), ("never chosen", None, "取消")):
            with self.subTest(why):
                clicked = []
                task = SimpleNamespace(width=1920, height=1080, log_info=lambda message: None, sleep=lambda seconds: None, click_box=clicked.append,
                                       all_texts=[FakeBox("Select 1 card with an Epiphany to reconstruct the Epiphany.", 0.5, 0.447, width=900),
                                                  FakeBox("取消", 0.347, 0.672), FakeBox("确认", 0.666, 0.672)])
                if decided is not None:
                    meditation.decide(task, decided)
                self.assertIs(True, meditation.handle_meditation_popup(task))
                self.assertEqual([expected], [box.name for box in clicked])

    def test_each_handler_runs_ahead_of_its_anchor_in_both_modes(self):
        # Behind its anchor, upstream's centre Confirm or Epiphany picker answers the screen first. The install only finds lists in
        # `sys.modules`, which another module in a shared run can clear, so the modes this file imported are put back for it.
        with mock.patch.dict(sys.modules, {"utils_chaos": utils_chaos, "utils_sortie": utils_sortie}):
            meditation.install(utils)
        for module in (utils_chaos, utils_sortie):
            names = [handler.__name__ for handler in module.PAGE_HANDLERS]
            for handler, anchors in (("handle_meditation", meditation.SAFE_ZONE_ANCHORS), ("handle_meditation_popup", (meditation.POPUP_ANCHOR,)),
                                     ("handle_meditation_pick", (meditation.PICK_ANCHOR,))):
                with self.subTest(module=module.__name__, handler=handler):
                    anchor = next(name for name in anchors if name in names)
                    self.assertLess(names.index(handler), names.index(anchor))


if __name__ == "__main__":
    unittest.main()
