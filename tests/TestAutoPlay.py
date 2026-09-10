"""Check that recording a Chaos battle never gets in the way of the run that is being recorded.

The recorder writes down hands, not decisions, and it is fire-and-forget by contract: it logs its first error
and swallows everything after. What can be reconstructed from a recording afterwards is `src/en/autoplay.py`,
which is offline-only and exercised by `scripts/study_auto.py` rather than from here.
"""

import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import observe  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
