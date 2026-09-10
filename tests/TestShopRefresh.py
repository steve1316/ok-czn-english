"""Check that the shop stops spending refreshes it can never afford to use.

The shop's refresh is free, so upstream takes it whenever nothing on the shelf matches. A run holding almost
nothing burns every refresh that way and then leaves anyway. The floor is what stops that, and hiding the
button rather than skipping the click afterwards is what keeps `handle_leave` - the next handler in the list -
free to walk out.

The floor is inclusive: holding exactly it is still worth a reroll. It is set where the user wants the run to
give up, not where the price list says a purchase becomes possible.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.shop import SHOP_FLOOR, free_refresh_box, refusing_free_refresh  # noqa: E402

# What the run is asked to keep refreshing down to.
WANTED_FLOOR = 29

WIDTH, HEIGHT = 1920, 1080
# Where the shop draws its free-refresh button, measured off the captured screen.
FREE_X, FREE_Y = 0.163, 0.933
# A shelf price sits well above the refresh band and must never be mistaken for the button.
SHELF_X, SHELF_Y = 0.500, 0.850


class FakeBox:
    """An OCR box positioned by its centre, the way the shop reads one."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 90, 30
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


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

    def test_hides_the_button_below_the_floor(self):
        seen = []
        wrapped = refusing_free_refresh(recording_handler(seen), lambda task: 0)
        wrapped(shop_screen())
        self.assertEqual(seen, [["96"]])

    def test_hides_the_button_one_credit_below_the_floor(self):
        seen = []
        wrapped = refusing_free_refresh(recording_handler(seen), lambda task: SHOP_FLOOR - 1)
        wrapped(shop_screen())
        self.assertEqual(seen, [["96"]])

    def test_keeps_the_button_exactly_at_the_floor(self):
        # The floor is inclusive: holding exactly it is still worth a reroll.
        seen = []
        wrapped = refusing_free_refresh(recording_handler(seen), lambda task: SHOP_FLOOR)
        wrapped(shop_screen())
        self.assertEqual(seen, [["96", "免费"]])

    def test_keeps_the_button_one_credit_above_the_floor(self):
        seen = []
        wrapped = refusing_free_refresh(recording_handler(seen), lambda task: SHOP_FLOOR + 1)
        wrapped(shop_screen())
        self.assertEqual(seen, [["96", "免费"]])

    def test_the_floor_is_where_it_was_asked_to_be(self):
        self.assertEqual(WANTED_FLOOR, SHOP_FLOOR)

    def test_keeps_the_button_above_the_floor(self):
        seen = []
        wrapped = refusing_free_refresh(recording_handler(seen), lambda task: 200)
        wrapped(shop_screen())
        self.assertEqual(seen, [["96", "免费"]])

    def test_does_not_read_credits_without_a_button(self):
        # Reading credits on every frame would cost two lookups for nothing, since the handler declines
        # immediately on any screen that is not the shop.
        def unexpected(task):
            raise AssertionError("credits were read with no refresh button on screen")

        wrapped = refusing_free_refresh(recording_handler([]), unexpected)
        self.assertTrue(wrapped(shop_screen(free=False)))


if __name__ == "__main__":
    unittest.main()
