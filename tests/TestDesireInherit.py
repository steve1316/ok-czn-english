"""Check the screen where two Desire cards merge into one.

Taking a card of a faction a combatant already carries just levels their card up. Taking a *different* one
opens this screen: both cards are shown with the tag they would end up with, and one of them has to be picked
to carry the merge. A captured pair read `[ Control / Inquiry 2 ]` and `[ Inquiry 2 / Control ]` - the same
points either way, so the faction outcome is settled before the screen even appears and the only thing being
chosen is which card's effect stays in the deck.

Today the screen is misread. Its title is `Card Reward`, so the ordinary reward handler claims it, finds no
priority match and presses Skip - throwing the merge away. It has to be claimed ahead of that handler.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.desire import INHERIT_TITLE, inherit_handler, keeper  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
# The two cards, measured off the run that met this screen.
CARD_X = (0.2698, 0.6469)
CARD_Y = 0.3148
TITLE_Y = 0.145


class FakeBox:
    """An OCR box positioned by its centre."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 200, 30
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


class FakeTask:
    """A task holding one OCR pass of the inherit screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes
        self.clicked = None
        self.slept = 0

    def sleep(self, seconds):
        self.slept += seconds

    def log_info(self, message):
        pass


def screen(tags, title=INHERIT_TITLE, confirm_active=False, priority=()):
    """Build the inherit screen and the stubs the handler reads through.

    Args:
        tags: One tag string per card, left to right.
        title: The prompt drawn at the top.
        confirm_active: Whether a card has already been picked.
        priority: The user's card reward priority list.

    Returns:
        A `(task, handler)` pair.
    """
    cards, boxes = [], [FakeBox(title, 0.5, TITLE_Y)]
    for index, tag in enumerate(tags):
        x = CARD_X[index]
        region = (x - 0.0565, CARD_Y + 0.1190, x + 0.1495, CARD_Y + 0.4900)
        name = f"card{index}"
        cards.append({"name": name, "x": x, "y": CARD_Y, "description_region": region})
        boxes.append(FakeBox(name, x, CARD_Y - 0.06))
        if tag is not None:
            boxes.append(FakeBox(tag, (region[0] + region[2]) / 2, (region[1] + region[3]) / 2))
    task = FakeTask(boxes)

    def move_and_click(task_, x, y):
        task_.clicked = (round(x, 4), round(y, 4))

    utils = types.SimpleNamespace(
        recognize_cards=lambda task_, **kwargs: cards,
        find_box_at_point=lambda task_, x, y: FakeBox("确认", x, y),
        is_button_active=lambda task_, box: confirm_active,
        _move_and_click=move_and_click,
        _get_config_value=lambda task_, key, default: default,
        _get_card_list=lambda task_, key: list(priority),
    )
    return task, inherit_handler(utils)


class TestKeeper(unittest.TestCase):
    """Choosing which card carries the merge."""

    @staticmethod
    def cards(*pairs):
        """Build cards carrying tags.

        Args:
            *pairs: One `(name, tags)` pair per card.

        Returns:
            A list of card dicts.
        """
        return [{"name": name, "tags": tags} for name, tags in pairs]

    def test_the_priority_list_decides(self):
        cards = self.cards(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("b", keeper(cards, ["b"])["name"])

    def test_the_priority_list_is_an_order(self):
        cards = self.cards(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", keeper(cards, ["a", "b"])["name"])

    def test_falls_back_to_the_higher_level_card(self):
        # Both end with the same faction points, so the level is the only thing left worth reading.
        cards = self.cards(("a", {"Control": 1}), ("b", {"Control": 1, "Inquiry": 2}))
        self.assertEqual("b", keeper(cards, [])["name"])

    def test_falls_back_to_the_first_card(self):
        cards = self.cards(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", keeper(cards, [])["name"])

    def test_nothing_offered_is_nothing_chosen(self):
        self.assertIsNone(keeper([], []))


class TestInheritHandler(unittest.TestCase):
    """Claiming the screen."""

    def test_picks_the_card_on_the_priority_list(self):
        task, handler = screen(["[ Control / Inquiry 2 ]", "[ Inquiry 2 / Control ]"], priority=["card1"])
        self.assertTrue(handler(task))
        self.assertEqual((round(CARD_X[1], 4), round(CARD_Y, 4)), task.clicked)

    def test_never_skips_the_merge(self):
        # Skipping is what upstream does today, and it throws away points already earned.
        task, handler = screen(["[ Control ]", "[ Inquiry ]"])
        self.assertTrue(handler(task))
        self.assertIsNotNone(task.clicked)

    def test_stands_aside_once_something_is_picked(self):
        task, handler = screen(["[ Control ]", "[ Inquiry ]"], confirm_active=True)
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_declines_an_ordinary_card_reward(self):
        # The two screens share a title, so only the prompt tells them apart.
        task, handler = screen(["[ Control ]", "[ Inquiry ]"], title="Card Reward")
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_reads_the_prompt_without_its_full_stop(self):
        task, handler = screen(["[ Control ]", "[ Inquiry ]"],
                               title="Please select the Desire Card to inherit")
        self.assertTrue(handler(task))

    def test_settles_after_picking(self):
        task, handler = screen(["[ Control ]", "[ Inquiry ]"])
        handler(task)
        self.assertGreater(task.slept, 0)


if __name__ == "__main__":
    unittest.main()
