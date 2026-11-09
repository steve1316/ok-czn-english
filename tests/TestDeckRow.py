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
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402

from src.en.deck import (  # noqa: E402
    COPY_LIST, GAP_KEY, PORTRAIT, ROW_TOLERANCE, choosing_copies, copying_ap_cards, portrait_of, preferring_target_row, random_combatant, reading_bottom_right_first, row_of,
    rows_first,
)
from src.en import deck  # noqa: E402
from src.en.handlers import standing_in  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

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
        self.matches = 0

    def feature_exists(self, name):
        return self._has_feature and name == PORTRAIT

    def find_one(self, feature_name=None, box=None, threshold=None):
        self.matches += 1
        return None if self._portrait_y is None else FakeFeature(self._portrait_y)

    def box_of_screen(self, *region):
        return region


def card(name, y):
    """Build the card dict the deck recognizer produces.

    Args:
        name: The card's name.
        y: The card's centre height, normalised.

    Returns:
        A dict with the keys the row preference reads.
    """
    return {"name": name, "x": 0.5, "y": y}


class TestPortraitOf(unittest.TestCase):
    """Finding the kept combatant's row."""

    def row(self, task):
        """Read the row height the way the wrapper does.

        Args:
            task: The screen to read.

        Returns:
            The row's centre height, or None.
        """
        return row_of(task, portrait_of(task))

    def test_reports_the_portrait_height(self):
        self.assertAlmostEqual(0.4, self.row(FakeTask(portrait_y=0.4)))

    def test_returns_none_without_a_captured_portrait(self):
        self.assertIsNone(self.row(FakeTask(portrait_y=0.4, has_feature=False)))

    def test_returns_none_when_the_portrait_is_off_screen(self):
        self.assertIsNone(self.row(FakeTask(portrait_y=None)))

    def test_does_not_match_at_all_without_the_template(self):
        # `feature_exists` is the cheap gate; matching a template that was never saved would just fail slowly.
        task = FakeTask(portrait_y=0.4, has_feature=False)
        portrait_of(task)
        self.assertEqual(0, task.matches)


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


class TestBottomRightFirst(unittest.TestCase):
    """Which copy of a card a pick takes when the page shows more than one."""

    def test_upstream_takes_the_bottom_right_copy(self):
        """Real upstream `select_card` over a one-page grid, its cards in the x order its recognizer returns them."""
        page = [dict(card("Sword Slash", y), x=x, selected=False, feature_name="attack_in_deck", type="", description="")
                for x, y in ((0.33, 0.1736), (0.33, 0.5935), (0.66, 0.1740), (0.66, 0.5931))]
        clicks = []
        task = types.SimpleNamespace(ocr=lambda: [], box_of_screen=lambda *a: None, log_info=lambda m: None,
                                     sleep=lambda s: None, feature_exists=lambda n: False, all_texts=[])
        with standing_in(utils, recognize_cards_in_deck=lambda *a, **k: [dict(c) for c in page],
                         _simplify_texts=lambda texts: texts, region_white_ratio=lambda *a: 0.0,
                         _move_and_click=lambda task_, x, y: clicks.append((x, y)),
                         _get_config_value=lambda task_, key, default: default, _get_game_text=lambda task_, key: key):
            self.assertTrue(reading_bottom_right_first(utils.select_card, utils)(task, ["Sword Slash"], count=2, action="复制"))
        self.assertEqual([(0.66, 0.5931), (0.33, 0.5935)], clicks)


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

    def test_only_the_operations_worth_steering_get_the_row_rule(self):
        """The kept combatant's row goes first for a removal or an Epiphany, and nowhere else."""
        for description, action, expected in (
            ("a removal", "移除", (True, ["low", "top"])),
            ("an epiphany", "闪光", (True, ["low", "top"])),
            ("the second epiphany wording", "灵光", (True, ["low", "top"])),
            ("any other operation", "复制", (False, ["top", "low"])),
        ):
            with self.subTest(description):
                self.assertEqual(expected, self.run_action(action))

    def test_does_not_look_for_the_portrait_on_other_operations(self):
        task = FakeTask(portrait_y=0.8)
        preferring_target_row(lambda *a, **k: True, self.utils_stub())(task, [], action="复制")
        self.assertEqual(0, task.matches)

    def test_matches_the_portrait_once_and_answers_upstream_from_that(self):
        # Answering the flag makes upstream look the same portrait up again; it must not be re-matched.
        utils = self.utils_stub()
        task = FakeTask(portrait_y=0.8)

        def select_card(task_, card_names, count=1, action=""):
            for _ in range(2):
                task_.find_one(feature_name=PORTRAIT, box=None, threshold=0.6)
            return True

        preferring_target_row(select_card, utils)(task, [], action="移除")
        self.assertEqual(1, task.matches)

    def test_other_feature_lookups_still_reach_the_task(self):
        utils = self.utils_stub()
        task = FakeTask(portrait_y=0.8)

        def select_card(task_, card_names, count=1, action=""):
            task_.find_one(feature_name="something_else", box=None, threshold=0.6)
            return True

        preferring_target_row(select_card, utils)(task, [], action="移除")
        self.assertEqual(2, task.matches)

    def test_stands_right_down_without_a_portrait(self):
        # Not just the grid: the flag must not be answered either, or upstream would turn on a row rule that
        # is about to fail its own portrait lookup anyway.
        self.assertEqual((False, ["top", "low"]), self.run_action("移除", portrait_y=None))

    def test_other_settings_still_read_normally(self):
        utils = self.utils_stub()
        seen = []

        def select_card(task, card_names, count=1, action=""):
            seen.append(utils._get_config_value(task, "优先移除基础牌", True))
            return True

        preferring_target_row(select_card, utils)(FakeTask(portrait_y=0.8), [], action="移除")
        self.assertEqual([True], seen)


class TestCopyingApCards(unittest.TestCase):
    """A copy with nothing on the user's list takes a pinned card, an AP card or the strongest, rather than skipping."""

    def test_only_a_copy_falls_back_to_ap_cards(self):
        # Appended to a removal, the same list would delete Source of Water from the deck.
        for action, expected in (("复制", True), ("移除", False), ("闪光", False)):
            with self.subTest(action):
                seen = []
                copying_ap_cards(lambda task, names, count=1, action="": seen.extend(names))(None, ["Ignition Slash"], action=action)
                self.assertEqual("Ignition Slash", seen[0])
                self.assertEqual(expected, "Source of Water" in seen)
                self.assertNotIn("Seven Arms", seen, "its AP comes with a condition")

    def copied(self, offered):
        """Run upstream's copy screen on an empty list and say which offered card it tapped."""
        clicked = []
        task = types.SimpleNamespace(log_info=lambda *a: None, sleep=lambda *a: None)
        with standing_in(utils, find_box_at_point=lambda *a: FakeBox("请选择要复制的卡牌", 0.498, 0.133), _get_game_text=lambda task_, text: text,
                         find_target_card=lambda task_: ([], []), recognize_cards=lambda task_, page="": offered,
                         _get_config_value=lambda task_, key, default: [] if key == COPY_LIST else default,
                         _move_and_click=lambda task_, x, y: clicked.append((x, y))):
            self.assertTrue(choosing_copies(utils.handle_copy_card_choice, utils)(task))
        return [card["name"] for card in offered if (card["x"], card["y"]) in clicked]

    def test_upstreams_copy_screen_falls_back_instead_of_skipping(self):
        # The last two are the 2026-11-08 run's own reads, where every Duplicate was skipped.
        for reason, offered, expected in (
            ("an AP card", [{"name": "Brand of Annihilation"}, {"name": "+Source of Water"}], "+Source of Water"),
            ("a pin over an AP card", [{"name": "+Source of Water"}, {"name": "Tsukuyomi", "pinned": True}], "Tsukuyomi"),
            ("the strongest as shown", [{"name": "Karmic Flames", "description": "[Initiation] 112% Damage × 2 1 Cursed Shackles"},
                                        {"name": "Oni Hunt", "description": "Haste 168% Damage ×2 +120% Damage Amount to the next Bind card"},
                                        {"name": "Tsukuyomi", "description": "3 Will-O'-Wisp for each Hit of the next Attack"}], "Oni Hunt"),
            ("an unread pin is never matched", [{"name": "", "pinned": True}, {"name": "Tsukuyomi"}, {"name": "Shadow of the Moon", "description": "78%Damage ×3"}],
             "Shadow of the Moon"),
        ):
            with self.subTest(reason):
                for column, card in enumerate(offered):
                    card.update(x=0.2 + column * 0.25, y=0.33)
                self.assertEqual([expected], self.copied(offered))

    def deck_grid(self, action, offered):
        """Run upstream's deck grid over a one-page deck carrying a Skip button, and say what it tapped."""
        tapped, skipped = [], []
        task = types.SimpleNamespace(name="", width=1920, height=1080, log_info=lambda *a: None, sleep=lambda *a: None, click_box=skipped.append,
                                     ocr=lambda: [FakeBox("跳过", 0.9, 0.93)],
                                     box_of_screen=lambda left, top, right, bottom: types.SimpleNamespace(x=left * 1920, y=top * 1080, width=(right - left) * 1920, height=(bottom - top) * 1080))
        with standing_in(utils, _simplify_texts=list, _get_config_value=lambda task_, key, default: default, _get_card_list=lambda task_, key: [],
                         _get_game_text=lambda task_, text: text, region_white_ratio=lambda *a: 0, recognize_cards_in_deck=lambda task_, page="": offered,
                         _move_and_click=lambda task_, x, y: tapped.append((x, y))):
            deck.copying_instead_of_skipping(utils.select_card, utils)(task, [], action=action)
        return tapped, len(skipped)

    def test_the_deck_grid_copies_the_strongest_card_rather_than_skipping(self):
        # All 5 deck-grid Duplicates in the September release logs ended on Skip.
        weak = {"name": "Karmic Flames", "description": "112% Damage", "x": 0.3, "y": 0.3, "selected": False}
        strong = {"name": "Oni Hunt", "description": "168% Damage ×2", "x": 0.6, "y": 0.3, "selected": False}
        unread = {"name": "", "description": "", "x": 0.3, "y": 0.6, "selected": False}
        for reason, action, offered, expected in (
            ("a copy takes the strongest", "复制", [weak, strong], ([(0.6, 0.3)], 0)),
            ("only a copy changes", "闪光", [weak, strong], ([], 1)),
            ("nothing readable to copy still skips", "复制", [unread], ([], 1)),
        ):
            with self.subTest(reason):
                self.assertEqual(expected, self.deck_grid(action, offered))


class TestDuplicateCombatant(unittest.TestCase):
    """The Duplicate's combatant is the save target when it shows, and a random one otherwise, rather than always the left-most."""

    def first_tap(self, target_x=None):
        clicked = []
        task = types.SimpleNamespace(log_info=lambda *a: None, sleep=lambda *a: None, width=WIDTH, height=HEIGHT, box_of_screen=lambda *r: r,
                                     feature_exists=lambda name: target_x is not None, wait_feature=lambda *a, **k: True,
                                     find_one=lambda **k: types.SimpleNamespace(x=target_x * WIDTH - 50, y=0.4 * HEIGHT - 50, width=100, height=100, confidence=0.9))
        with standing_in(utils, find_box_at_point=lambda *a: FakeBox("请选择要复制卡牌的主战员", 0.502, 0.932), _get_game_text=lambda task_, text: text,
                         _move_and_click=lambda task_, x, y: clicked.append(x)):
            with standing_in(deck.random, sample=lambda population, k: list(reversed(population))):
                self.assertTrue(random_combatant(utils.handle_copy_member, utils)(task))
        return clicked[0]

    def test_a_random_combatant_unless_the_save_target_shows(self):
        for reason, target_x, expected in (("no target, so the shuffle", None, 0.755), ("the target still wins", 0.228, 0.228)):
            with self.subTest(reason):
                self.assertEqual(expected, self.first_tap(target_x))


if __name__ == "__main__":
    unittest.main()
