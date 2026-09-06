"""Check what the picker does with a hand once a turn is under way.

`cards.py` decides what a hand is worth. This is the layer above it: which card actually gets a key pressed
for it, what happens when the game refuses one, and when a turn should just be ended.
"""

import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import battle, cards, overrides  # noqa: E402

ATTACK = "Anchor"
BIG_ATTACK = "Charge Launcher"
CURSE = "Anemia"


def hand(*names_in_order, keyless=()):
    """Build a hand the way `_hand_cards` hands one over.

    Args:
        names_in_order: Card names, left to right as they sit on screen.
        keyless: Names whose hotkey the reader failed to pair up, so they cannot be played.

    Returns:
        A list of hand-card dicts.
    """
    return [{"name": name, "key": None if name in keyless else str(index + 1)}
            for index, name in enumerate(names_in_order)]


class TestChoosing(unittest.TestCase):
    """Which card gets played, given what the turn has already learnt."""

    def test_the_best_card_is_chosen(self):
        chosen = battle.choose(hand(ATTACK, BIG_ATTACK), cards.Board(), set())
        self.assertEqual(chosen["name"], BIG_ATTACK)

    def test_a_refused_card_is_passed_over(self):
        # The game would not play it earlier in this turn, so trying it again only wastes the frame.
        chosen = battle.choose(hand(ATTACK, BIG_ATTACK), cards.Board(), {BIG_ATTACK})
        self.assertEqual(chosen["name"], ATTACK)

    def test_a_card_with_no_hotkey_is_passed_over(self):
        # There is no way to press a key the reader never found.
        chosen = battle.choose(hand(BIG_ATTACK, ATTACK, keyless=(BIG_ATTACK,)), cards.Board(), set())
        self.assertEqual(chosen["name"], ATTACK)

    def test_nothing_left_ends_the_turn(self):
        self.assertIsNone(battle.choose(hand(ATTACK), cards.Board(), {ATTACK}))

    def test_a_hand_of_curses_ends_the_turn(self):
        self.assertIsNone(battle.choose(hand(CURSE), cards.Board(), set()))

    def test_an_empty_hand_ends_the_turn(self):
        self.assertIsNone(battle.choose([], cards.Board(), set()))


class TestTurnTracking(unittest.TestCase):
    """Telling a card the game would not play apart from one it did, and both apart from a fresh turn."""

    def test_a_card_still_in_hand_was_refused(self):
        # Counting the hand is not enough: a card that draws replaces itself, so the count can stay the same
        # on a card that played perfectly well. Whether the card itself is still there is the real answer.
        self.assertTrue(battle.was_refused(ATTACK, [ATTACK, BIG_ATTACK]))

    def test_a_card_gone_from_hand_was_played(self):
        self.assertFalse(battle.was_refused(ATTACK, [BIG_ATTACK]))

    def test_a_card_that_drew_another_is_not_a_refusal(self):
        self.assertFalse(battle.was_refused(ATTACK, [BIG_ATTACK, CURSE]))

    def test_nothing_attempted_is_not_a_refusal(self):
        self.assertFalse(battle.was_refused(None, [ATTACK]))

    def test_a_bigger_hand_means_a_new_turn(self):
        self.assertTrue(battle.new_turn(before=1, after=5))

    def test_the_same_hand_is_not_a_new_turn(self):
        self.assertFalse(battle.new_turn(before=5, after=5))

    def test_a_shrinking_hand_is_not_a_new_turn(self):
        self.assertFalse(battle.new_turn(before=5, after=4))

    def test_the_first_frame_of_a_battle_is_a_new_turn(self):
        self.assertTrue(battle.new_turn(before=None, after=5))


class Pressed:
    """A task that records what was sent to the game instead of sending it."""

    def __init__(self, hand_cards, smart=True):
        self.hand_cards = hand_cards
        self.config = {overrides.SMART_CARD_PLAY: smart}
        # A fresh list per frame, the way `SortieMode.run` rebinds it after every OCR pass.
        self.all_texts = []
        self.keys = []
        self.logged = []

    def send_key(self, key):
        self.keys.append(key)

    def sleep(self, seconds):
        pass

    def log_info(self, message):
        self.logged.append(message)


@contextmanager
def upstream(hand_cards, smart=True):
    """Stand the two upstream modules up in `sys.modules` so the install has something to patch.

    Args:
        hand_cards: What `_hand_cards` should report.
        smart: What the Smart Card Play setting reads as.

    Yields:
        The fake `utils_sortie` module and the task the replacement is called with.
    """
    utils = types.ModuleType("utils")
    utils._get_config_value = lambda task, key, default: task.config.get(key, default)
    utils_sortie = types.ModuleType("utils_sortie")
    utils_sortie._hand_cards = lambda task: task.hand_cards
    utils_sortie.name_reads = []
    utils_sortie._hand_card_names = lambda task: utils_sortie.name_reads.append(task.all_texts) or []
    utils_sortie.blind_calls = []
    utils_sortie._try_all_card_keys = lambda task, count: utils_sortie.blind_calls.append(count)
    saved = {name: sys.modules.get(name) for name in ("utils", "utils_sortie")}
    sys.modules["utils"], sys.modules["utils_sortie"] = utils, utils_sortie
    try:
        yield utils_sortie, Pressed(hand_cards, smart)
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class TestInstalling(unittest.TestCase):
    """The patch itself. A replacement that silently fails to install would look exactly like working code."""

    def test_the_blind_fallback_is_replaced(self):
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            self.assertTrue(getattr(utils_sortie._try_all_card_keys, "_en_picker", False))

    def test_installing_again_does_not_wrap_the_replacement(self):
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            once = utils_sortie._try_all_card_keys
            battle.install()
            self.assertIs(utils_sortie._try_all_card_keys, once)

    def test_the_chosen_card_gets_its_hotkey_pressed(self):
        with upstream(hand(ATTACK, BIG_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, len(task.hand_cards))
            # Charge Launcher is the better buy, and it is the second card, so key 2 then the confirm.
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY])

    def test_a_hand_of_curses_ends_the_turn(self):
        with upstream(hand(CURSE)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 1)
            self.assertEqual(task.keys, [battle.END_TURN_KEY])

    def test_switching_it_off_hands_back_to_upstream(self):
        with upstream(hand(ATTACK), smart=False) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 4)
            self.assertEqual(task.keys, [])
            self.assertEqual(utils_sortie.blind_calls, [4])

    def test_the_hand_is_only_read_once_for_one_ocr_pass(self):
        # Upstream reads the hand twice a frame and the picker would make it three. Each read logs a line per
        # box on screen, so on the busiest screen in the game that is the difference worth removing.
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._hand_card_names(task)
            utils_sortie._hand_card_names(task)
            self.assertEqual(len(utils_sortie.name_reads), 1)

    def test_the_next_ocr_pass_reads_the_hand_again(self):
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._hand_card_names(task)
            task.all_texts = []
            utils_sortie._hand_card_names(task)
            self.assertEqual(len(utils_sortie.name_reads), 2)

    def test_a_card_still_in_hand_is_not_tried_again(self):
        with upstream(hand(ATTACK, BIG_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            # The game kept it, so the next frame should reach for the other card instead.
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY, "1", battle.CONFIRM_KEY])


if __name__ == "__main__":
    unittest.main()
