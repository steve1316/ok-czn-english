"""Check that card screens favour the combatant whose save data the run is keeping.

The deck grid is laid out one row per combatant. Upstream can already prefer a row - it finds the save-scum
target's portrait down the left of the screen and matches cards by height against it - but only while the
`刷空档` strategy is switched on, and only when removing. Since the run discards every other combatant's save
data, that row is the one worth acting on whatever the strategy, and on Epiphany screens as well.

The tolerance and the portrait feature are upstream's own, so both are pinned here.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.deck import (  # noqa: E402
    GAP_KEY, PORTRAIT, ROW_ACTIONS, ROW_TOLERANCE, preferring_target_row, rows_first, target_row_y,
)

WIDTH, HEIGHT = 1920, 1080


class FakeFeature:
    """A template match, positioned the way `find_one` reports one."""

    def __init__(self, center_y):
        self.width, self.height = 100, 120
        self.x = 200
        self.y = center_y * HEIGHT - self.height / 2
        self.confidence = 0.83


class FakeTask:
    """A task that can answer for the save-scum portrait."""

    width, height = WIDTH, HEIGHT

    def __init__(self, portrait_y=None, has_feature=True):
        self.all_texts = []
        self._portrait_y = portrait_y
        self._has_feature = has_feature
        self.logged = []

    def feature_exists(self, name):
        return self._has_feature and name == PORTRAIT

    def find_one(self, feature_name=None, box=None, threshold=None):
        return None if self._portrait_y is None else FakeFeature(self._portrait_y)

    def box_of_screen(self, *region):
        return region

    def log_info(self, message):
        self.logged.append(message)


def card(name, y):
    """Build the card dict the deck recognizer produces.

    Args:
        name: The card's name.
        y: The card's centre height, normalised.

    Returns:
        A dict with the keys the row preference reads.
    """
    return {"name": name, "x": 0.5, "y": y}


class TestTargetRowY(unittest.TestCase):
    """Finding the kept combatant's row."""

    def test_reports_the_portrait_height(self):
        self.assertAlmostEqual(0.4, target_row_y(FakeTask(portrait_y=0.4)))

    def test_returns_none_without_a_captured_portrait(self):
        self.assertIsNone(target_row_y(FakeTask(portrait_y=0.4, has_feature=False)))

    def test_returns_none_when_the_portrait_is_off_screen(self):
        self.assertIsNone(target_row_y(FakeTask(portrait_y=None)))


class TestRowsFirst(unittest.TestCase):
    """Ordering the grid so that row comes first."""

    def test_moves_the_rows_cards_to_the_front(self):
        cards = [card("a", 0.20), card("b", 0.60), card("c", 0.25), card("d", 0.90)]
        self.assertEqual(["b", "d", "a", "c"], [c["name"] for c in rows_first(cards, 0.75)])

    def test_keeps_the_order_within_each_group(self):
        cards = [card("a", 0.20), card("b", 0.22), card("c", 0.90), card("d", 0.92)]
        self.assertEqual(["a", "b", "c", "d"], [c["name"] for c in rows_first(cards, 0.21)])

    def test_leaves_the_order_alone_without_a_row(self):
        cards = [card("a", 0.20), card("b", 0.90)]
        self.assertEqual(cards, rows_first(cards, None))

    def test_uses_upstreams_own_tolerance(self):
        # A card exactly at the edge of the band still counts as being on the row.
        cards = [card("far", 0.10), card("edge", 0.10 + ROW_TOLERANCE)]
        self.assertEqual(["edge", "far"], [c["name"] for c in rows_first(cards, 0.10 + 2 * ROW_TOLERANCE)])


class TestPreferringTargetRow(unittest.TestCase):
    """What `select_card` is told for the length of one call."""

    @staticmethod
    def utils_stub():
        """Build a stand-in carrying the two seams this patch moves.

        Returns:
            A namespace with `_get_config_value` and `recognize_cards_in_deck`.
        """
        return types.SimpleNamespace(
            _get_config_value=lambda task_, key, default: default,
            recognize_cards_in_deck=lambda task_, **kwargs: [card("top", 0.20), card("low", 0.80)],
        )

    def run_action(self, action, portrait_y=0.80):
        """Run the wrapped `select_card` and report what it was shown.

        Args:
            action: The card operation, such as `移除`.
            portrait_y: Where the kept combatant's portrait sits, or None for absent.

        Returns:
            A `(gap_flag, card_names)` pair as upstream would have seen them.
        """
        utils = self.utils_stub()
        seen = {}

        def select_card(task, card_names, count=1, action=""):
            seen["gap"] = utils._get_config_value(task, GAP_KEY, False)
            seen["cards"] = [c["name"] for c in utils.recognize_cards_in_deck(task)]
            return True

        task = FakeTask(portrait_y=portrait_y)
        preferring_target_row(select_card, utils)(task, [], count=1, action=action)
        return seen["gap"], seen["cards"]

    def test_turns_on_the_row_rule_for_a_removal(self):
        self.assertEqual((True, ["low", "top"]), self.run_action("移除"))

    def test_orders_the_grid_for_an_epiphany(self):
        self.assertEqual((True, ["low", "top"]), self.run_action("闪光"))

    def test_covers_the_second_epiphany_wording(self):
        self.assertEqual((True, ["low", "top"]), self.run_action("灵光"))

    def test_leaves_other_operations_alone(self):
        self.assertEqual((False, ["top", "low"]), self.run_action("复制"))

    def test_leaves_the_grid_alone_without_a_portrait(self):
        self.assertEqual((True, ["top", "low"]), self.run_action("移除", portrait_y=None))

    def test_actions_are_the_ones_the_user_asked_for(self):
        self.assertEqual({"移除", "闪光", "灵光"}, set(ROW_ACTIONS))

    def test_restores_both_seams_afterwards(self):
        utils = self.utils_stub()
        config, recognise = utils._get_config_value, utils.recognize_cards_in_deck
        preferring_target_row(lambda *a, **k: True, utils)(FakeTask(portrait_y=0.8), [], action="移除")
        self.assertIs(utils._get_config_value, config)
        self.assertIs(utils.recognize_cards_in_deck, recognise)

    def test_restores_both_seams_when_select_card_raises(self):
        utils = self.utils_stub()
        config, recognise = utils._get_config_value, utils.recognize_cards_in_deck

        def raising(*args, **kwargs):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            preferring_target_row(raising, utils)(FakeTask(portrait_y=0.8), [], action="移除")
        self.assertIs(utils._get_config_value, config)
        self.assertIs(utils.recognize_cards_in_deck, recognise)

    def test_other_settings_still_read_normally(self):
        utils = self.utils_stub()
        seen = []

        def select_card(task, card_names, count=1, action=""):
            seen.append(utils._get_config_value(task, "优先移除基础牌", True))
            return True

        preferring_target_row(select_card, utils)(FakeTask(portrait_y=0.8), [], action="移除")
        self.assertEqual([True], seen)


if __name__ == "__main__":
    unittest.main()
