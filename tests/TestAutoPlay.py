"""Check that recording a Chaos battle never gets in the way of the run that is being recorded.

The recorder writes down hands, not decisions, and it is fire-and-forget by contract: it logs its first error
and swallows everything after. What can be reconstructed from a recording afterwards is `src/en/autoplay.py`,
which is offline-only and exercised by `scripts/study_auto.py` rather than from here.
"""

import sys
import types
import unittest
from contextlib import contextmanager
from unittest import mock
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils_sortie  # noqa: E402,F401
from ok.task.task import OCR  # noqa: E402

from src.en import autoplay, observe  # noqa: E402

# A real card name, so canonical folding is exercised rather than bypassed.
ATTACK = "Anchor"


class FakeTask:
    """A task on a battle screen, holding just what the recorder reads."""

    def __init__(self, hand_cards):
        self.hand_cards = hand_cards
        self.all_texts = []
        self.frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
        self.trigger_interval = 1
        self.height, self.width = self.frame.shape[:2]
        self.logged = []

    def log_info(self, message):
        self.logged.append(message)


@contextmanager
def chaos(hand_cards):
    """Stand the upstream modules up so the recorder has a handler to wrap.

    Args:
        hand_cards: What `_hand_cards` should report.

    Yields:
        The fake `utils_chaos` module and the task the wrapped handler is called with.
    """
    utils_sortie = types.ModuleType("utils_sortie")
    utils_sortie._hand_cards = lambda task: task.hand_cards
    utils_sortie._read_hand_count = lambda task: len(task.hand_cards)
    utils_chaos = types.ModuleType("utils_chaos")
    utils_chaos.on_battle = True

    def handle_battle_auto_check(task):
        """Stand in for upstream's Chaos battle frame."""
        return utils_chaos.on_battle

    utils_chaos.handle_battle_auto_check = handle_battle_auto_check
    utils_chaos.PAGE_HANDLERS = [handle_battle_auto_check]
    saved = {name: sys.modules.get(name) for name in ("utils_sortie", "utils_chaos")}
    sys.modules["utils_sortie"], sys.modules["utils_chaos"] = utils_sortie, utils_chaos
    try:
        yield utils_chaos, FakeTask(hand_cards)
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@contextmanager
def collected():
    """Catch what the recorder would have written instead of letting it touch the disk.

    Yields:
        A list that gains one record per frame written.
    """
    written = []
    saved, observe.write = observe.write, lambda task: written.append(observe.seen(task))
    try:
        yield written
    finally:
        observe.write = saved


def quad(x, y, width, height):
    """Build an OCR engine's corner list for a box.

    Args:
        x: The box's left edge in pixels.
        y: The box's top edge in pixels.
        width: The box's width in pixels.
        height: The box's height in pixels.

    Returns:
        The four corners, clockwise from the top left, as the engine reports them.
    """
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


class TestRecording(unittest.TestCase):
    """The recorder itself, which watches Chaos and must never get in its way."""

    def test_a_battle_frame_is_recorded(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            record = observe.seen(task)
            self.assertEqual(record["hand"], [[ATTACK, "1"]])

    def test_the_hand_count_comes_from_the_games_own_readout(self):
        # Not from the length of what the reader found. The two disagreeing is the signal that the hand
        # region picked up something that is not a card, which is the only way to catch a junk frame.
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            sys.modules["utils_sortie"]._read_hand_count = lambda task: 5
            self.assertEqual(observe.seen(task)["count"], 5)

    def test_a_readout_that_cannot_be_read_is_recorded_as_unknown(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            sys.modules["utils_sortie"]._read_hand_count = lambda task: None
            self.assertIsNone(observe.seen(task)["count"])

    def test_the_board_state_is_recorded(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            record = observe.seen(task)
            self.assertIn("points", record)
            self.assertIn("weakness", record)
            self.assertIn("at", record)

    def test_upstream_still_decides_whether_this_is_a_battle(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            with collected() as written:
                self.assertTrue(utils_chaos.PAGE_HANDLERS[0](task))
                utils_chaos.on_battle = False
                self.assertFalse(utils_chaos.PAGE_HANDLERS[0](task))
            self.assertEqual(len(written), 1)

    def test_nothing_is_written_when_it_is_not_a_battle_screen(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            utils_chaos.on_battle = False
            with collected() as written:
                utils_chaos.PAGE_HANDLERS[0](task)
            self.assertEqual(written, [])

    def test_a_recorder_that_throws_never_breaks_the_run(self):
        # Losing the data costs a capture session. Breaking Chaos costs a run, so the handler must survive
        # anything the recorder does.
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            def broken(task):
                raise RuntimeError("no disk")

            saved, observe.write = observe.write, broken
            try:
                self.assertTrue(utils_chaos.PAGE_HANDLERS[0](task))
            finally:
                observe.write = saved

    def test_a_battle_is_sampled_faster_than_the_rest_of_the_run(self):
        # Auto plays several cards a second. At upstream's one second pace most transitions lose two or more
        # cards at once, and which one it chose first is then unknowable.
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            with collected():
                utils_chaos.PAGE_HANDLERS[0](task)
            self.assertEqual(task.trigger_interval, observe.BATTLE_INTERVAL)

    def test_the_normal_pace_comes_back_off_the_battle_screen(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            with collected():
                utils_chaos.PAGE_HANDLERS[0](task)
                utils_chaos.on_battle = False
                utils_chaos.PAGE_HANDLERS[0](task)
            self.assertEqual(task.trigger_interval, 1)

    def test_installing_again_does_not_wrap_the_wrapper(self):
        with chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
            observe.install()
            once = utils_chaos.PAGE_HANDLERS[0]
            observe.install()
            self.assertIs(utils_chaos.PAGE_HANDLERS[0], once)

    def test_only_a_debug_run_grabs_the_hand_between_frames(self):
        # The grabs and their second OCR engine are a study aid. A release run paying for them gets nothing back.
        with mock.patch.object(observe.BURST, "battle_seen") as started:
            for debug in (False, True):
                with self.subTest(debug=debug), chaos([{"name": ATTACK, "key": "1"}]) as (utils_chaos, task):
                    task.debug = debug
                    observe.install()
                    with collected():
                        utils_chaos.PAGE_HANDLERS[0](task)
                    self.assertEqual(started.call_count, int(debug))


class TestBurst(unittest.TestCase):
    """The burst grabs, read back after the battle and merged into the recording."""

    def test_a_saved_band_reads_back_as_the_live_hand_would(self):
        # Against upstream's real hand reader, so a box left in band coordinates misses its region and comes back empty,
        # and a rename of anything the read-back leans on fails here rather than as a silent empty recording.
        left, top = observe.band_origin(1920, 1080)
        on_screen = [((500, 760, 120, 30), ATTACK), ((490, 715, 20, 25), "1"), ((960, 1035, 50, 30), "1/10")]
        engine = types.SimpleNamespace(ocr=lambda band: [[(quad(x - left, y - top, width, height), (text, 0.9))
                                                          for (x, y, width, height), text in on_screen]])
        task = types.SimpleNamespace(width=1920, height=1080, ocr_default_threshold=0.2, fix_texts=lambda boxes: None)
        task.get_box = OCR.get_box.__get__(task)
        record = observe.read_back(task, engine, np.zeros((432, 1420, 3), dtype=np.uint8), 5.0)
        self.assertEqual(record, {"at": 5.0, "hand": [[ATTACK, "1"]], "count": 1})

    def test_a_grab_borrows_the_board_of_the_frame_before_it(self):
        # A grab only reads the hand. Taking the defaults instead would claim Action Points on every grab, and a turn ended
        # into a fresh deal would then look like a draw.
        frames = [autoplay.Frame(at=1.0, hand=(("A", "1"), ("B", "2")), count=2, points=False, weakness="Justice"),
                  autoplay.Frame(at=3.0, hand=(), count=0)]
        grabs = [autoplay.Frame(at=2.0, hand=(("B", "1"),), count=1)]
        every = autoplay.merged(frames, grabs)
        self.assertEqual([frame.at for frame in every], [1.0, 2.0, 3.0])
        self.assertEqual(every[1], frames[0]._replace(at=2.0, hand=(("B", "1"),), count=1))


if __name__ == "__main__":
    unittest.main()
