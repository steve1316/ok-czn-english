"""Check that the shop stops spending refreshes it can never afford to use.

The shop's refresh is free, so upstream takes it whenever nothing on the shelf matches. A run holding almost
nothing burns every refresh that way and then leaves anyway. The floor is what stops that, and hiding the
button rather than skipping the click afterwards is what keeps `handle_leave` - the next handler in the list -
free to walk out.

The floor is inclusive: holding exactly it is still worth a reroll. It is set where the user wants the run to
give up, not where the price list says a purchase becomes possible. A negative paid-refresh threshold has to
mean "never", which upstream's own `handle_shop` is run against below.
"""

import sys
import types
import unittest
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.shop import (  # noqa: E402
    BUY_MONSTER_CARDS, PAID_THRESHOLD, SHOP_FLOOR, credits_read, free_refresh_box, leaving_monster_cards, never_paying, reading_names_whole,
    refusing_free_refresh, skipping_poor_shop,
)

WIDTH, HEIGHT = 1920, 1080
# Where the shop draws its free-refresh button, measured off the captured screen.
FREE_X, FREE_Y = 0.163, 0.933
# A shelf price sits well above the refresh band and must never be mistaken for the button.
SHELF_X, SHELF_Y = 0.500, 0.850
# Where `handle_shop` reads the sold-out card removal, the run's credits, the paid refreshes left and their price.
SOLD_OUT_X, SOLD_OUT_Y = 0.727, 0.286
CREDIT_X, CREDIT_Y = 0.794, 0.054
COUNT_X, PRICE_X, PAID_Y = 0.080, 0.190, 0.932
# Two shelf slots: the credit icon `handle_shop` clicks to buy, and the card type badge that marks the slot as a card.
SHELF_ICON_XS, SHELF_ICON_Y, BADGE_Y = (0.200, 0.500), 0.830, 0.730


# The shop places its boxes by share of the screen.
FakeBox = partial(Box, width=90, height=30, units="fraction")


class FakeTask:
    """A task holding one OCR pass of the shop screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes
        self.logged = []

    def log_info(self, message):
        self.logged.append(message)


def shop_screen(free=True):
    """Build the shop screen as the reader sees it.

    Args:
        free: Whether the free-refresh button is on screen.

    Returns:
        A `FakeTask`.
    """
    boxes = [FakeBox("96", SHELF_X, SHELF_Y)]
    if free:
        boxes.append(FakeBox("免费", FREE_X, FREE_Y))
    return FakeTask(boxes)


def recording_handler(seen):
    """Build a stand-in for `handle_shop` that records the pass it was given.

    Args:
        seen: The list to append each call's box names to.

    Returns:
        A handler returning True, the way upstream does when it clicks something.
    """
    def handler(task):
        seen.append([box.name for box in task.all_texts])
        return True

    return handler


class TestFreeRefreshBox(unittest.TestCase):
    """Finding the button in an OCR pass."""

    def test_finds_the_button_in_the_refresh_band(self):
        found = free_refresh_box(shop_screen())
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "免费")

    def test_ignores_the_same_word_outside_the_band(self):
        task = FakeTask([FakeBox("免费", SHELF_X, SHELF_Y)])
        self.assertIsNone(free_refresh_box(task))

    def test_returns_none_when_the_button_is_absent(self):
        self.assertIsNone(free_refresh_box(shop_screen(free=False)))


class TestRefusingFreeRefresh(unittest.TestCase):
    """What the wrapped handler lets upstream see."""

    # Only the button is hidden, never the screen: `handle_leave`, the next handler in the list, still has to
    # be free to walk out. The floor is inclusive, so holding exactly it is still worth a reroll.
    SHELF = ["96"]
    SHELF_AND_BUTTON = ["96", "免费"]
    CASES = (
        ("holding nothing", 0, SHELF),
        ("one credit below the floor", SHOP_FLOOR - 1, SHELF),
        ("exactly at the floor", SHOP_FLOOR, SHELF_AND_BUTTON),
        ("one credit above the floor", SHOP_FLOOR + 1, SHELF_AND_BUTTON),
        ("comfortably above the floor", 200, SHELF_AND_BUTTON),
    )

    def test_the_button_is_hidden_only_below_the_floor(self):
        for why, credits, expected in self.CASES:
            with self.subTest(why):
                seen = []
                wrapped = refusing_free_refresh(recording_handler(seen), lambda task, c=credits: c)
                wrapped(shop_screen())
                self.assertEqual(seen, [expected])

    def test_does_not_read_credits_without_a_button(self):
        # Reading credits on every frame would cost two lookups for nothing, since the handler declines
        # immediately on any screen that is not the shop.
        def unexpected(task):
            raise AssertionError("credits were read with no refresh button on screen")

        wrapped = refusing_free_refresh(recording_handler([]), unexpected)
        self.assertTrue(wrapped(shop_screen(free=False)))


class PaidRefreshTask(FakeTask):
    """The shop with its free refreshes spent, holding 500 credits against a 50-credit paid reroll."""

    name = "自动卡厄思模式"

    def __init__(self, threshold):
        self.price = FakeBox("50", PRICE_X, PAID_Y)
        super().__init__([FakeBox("售罄", SOLD_OUT_X, SOLD_OUT_Y), FakeBox("500", CREDIT_X, CREDIT_Y),
                          FakeBox("2/3", COUNT_X, PAID_Y), self.price])
        self.config = {PAID_THRESHOLD: threshold}
        self.node_status = {"shop": False}
        self.clicked = []

    def find_feature(self, *args, **kwargs):
        return []

    def box_of_screen(self, *args):
        return None

    def click_box(self, box):
        self.clicked.append(box)

    def sleep(self, seconds):
        pass


class TestNeverPaying(unittest.TestCase):
    """Upstream pays while credits are above the threshold, so -1 would pay on every visit without the wrap."""

    CASES = (("-1 never pays", -1, False), ("0 pays whenever affordable", 0, True), ("above the credits", 999, False))

    def test_only_a_reachable_threshold_pays(self):
        handler = never_paying(utils.handle_shop, utils)
        for why, threshold, pays in self.CASES:
            with self.subTest(why):
                task = PaidRefreshTask(threshold)
                handler(task)
                self.assertEqual(task.clicked, [task.price] if pays else [])


class MonsterShelfTask(PaidRefreshTask):
    """The shop with a Monster Card in the first slot and an ordinary card in the second, both on the card list."""

    SHELF = ("Dominion", "Absolute Zero")

    def __init__(self, buys_monsters):
        super().__init__(-1)
        self.icons = [FakeBox("", x, SHELF_ICON_Y, width=30, height=30) for x in SHELF_ICON_XS]
        self.badges = [FakeBox("", x, BADGE_Y, width=30, height=30) for x in SHELF_ICON_XS]
        for x, name in zip(SHELF_ICON_XS, self.SHELF):
            self.all_texts += [FakeBox(name, x + 0.050, 0.650), FakeBox("50", x + 0.099, SHELF_ICON_Y - 0.001)]
        self.config.update({"卡牌奖励优先级": list(self.SHELF), BUY_MONSTER_CARDS: buys_monsters})

    def find_feature(self, feature_name=None, **kwargs):
        return {"credit_icon": self.icons, "attack_in_shop": self.badges}.get(feature_name, [])


class TestLeavingMonsterCards(unittest.TestCase):
    """Upstream buys whatever on the shelf matches the card list first, Monster Card or not."""

    def test_the_switch_decides_whether_the_monster_card_is_bought(self):
        handler = leaving_monster_cards(utils.handle_shop, utils)
        for why, buys_monsters, slot in (("switched on", True, 0), ("switched off", False, 1)):
            with self.subTest(why):
                task = MonsterShelfTask(buys_monsters)
                handler(task)
                self.assertEqual(task.clicked, [task.icons[slot]])


class TestReadingNamesWhole(unittest.TestCase):
    """The shelf wraps a long name onto two lines, which OCR lists in either order."""

    CASES = (
        # Boxed exactly as OCR boxed the shelf, second line listed first.
        ("a wrapped name", [Box("Judgment", 1720, 735.5, width=140, height=39, units="pixels"),
                            Box("Instant", 1715, 700.5, width=98, height=33, units="pixels")], "Instant Judgment"),
        # A pixel higher on the right must not put the right-hand box first.
        ("one line in two boxes", [Box("Torch", 980, 740, width=90, height=33, units="pixels"),
                                   Box("Distortion:", 880, 741, width=110, height=33, units="pixels")], "Distortion: Torch"),
    )

    def test_a_name_is_read_line_by_line_with_spaces(self):
        for why, boxes, expected in self.CASES:
            with self.subTest(why):
                utils = types.SimpleNamespace(_get_region_text=None)
                seen = []
                wrapped = reading_names_whole(lambda task: seen.append(utils._get_region_text(task, (0, 0, 1, 1))), utils)
                wrapped(FakeTask(boxes))
                self.assertEqual(seen, [expected])



class TestSkippingPoorShop(unittest.TestCase):
    """The Safe Zone walks past the shop when the run cannot afford its cheapest item, which costs 35."""

    def test_the_shop_is_entered_only_from_the_floor_up(self):
        # An unread count is not zero: skipping on a misread would cost a shop the run could have used.
        for why, credit, entered in (("one credit short", "34", False), ("exactly the floor", "35", True), ("count unread", None, True)):
            with self.subTest(why):
                boxes = [FakeBox("德朗商店", 0.360, 0.138)] + ([FakeBox(credit, CREDIT_X, CREDIT_Y)] if credit else [])
                task = FakeTask(boxes)
                task.node_status = {"shop": True}
                seen = []
                skipping_poor_shop(lambda task: seen.append(task.node_status["shop"]), utils)(task)
                self.assertEqual([entered], seen)


class TestCreditsRead(unittest.TestCase):
    """Chaos draws the credits left of where upstream looks, so a fixed-point read saw 0 and the shop never paid for a removal."""

    CASES = (
        # Measured off a Chaos equipment screen: the Faint Memory shard count sits left of the credits and must not be taken.
        ("Chaos top bar", [FakeBox("1543/1543", 0.212, 0.052), FakeBox("9", 0.565, 0.052), FakeBox("1140", 0.647, 0.052)], 1140),
        ("Sortie top bar", [FakeBox("K", 0.684, 0.052), FakeBox("113", 0.734, 0.051)], 113),
        ("nothing read", [FakeBox("1543/1543", 0.212, 0.052)], None),
    )

    def test_the_credits_are_read_wherever_the_bar_puts_them(self):
        for why, boxes, expected in self.CASES:
            with self.subTest(why):
                self.assertEqual(credits_read(FakeTask(boxes)), expected)


if __name__ == "__main__":
    unittest.main()
