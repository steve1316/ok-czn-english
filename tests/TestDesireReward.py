"""Check the Desire card screen that used to stall a run.

`Select a Desire Card reward.` offers three cards and has no Skip - one of them must be taken. No handler
claimed it, so the run sat on a greyed-out Confirm once a second until the stuck-screen fallback fired ten
seconds later and clicked a card at random. That fallback is the only reason a run got past this screen at
all, and a random Desire pick is close to the worst outcome the mechanic allows, because the faction chosen
here is what the rest of the run compounds on.

The screen is claimed here instead, ahead of the confirm handler, and the card carrying the faction being
chased is taken. Positions are the captured screen's.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.desire import REWARD_TITLE, best, reward_handler  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
# The three cards the screen offers, measured off the run that stalled on it.
CARD_X = (0.1927, 0.4661, 0.7396)
CARD_Y = 0.2713
TITLE_Y = 0.145


class FakeBox:
    """An OCR box positioned by its centre."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 200, 30
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


class FakeTask:
    """A task holding one OCR pass of a Desire screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes
        self.clicked = None
        self.slept = 0

    def sleep(self, seconds):
        self.slept += seconds

    def log_info(self, message):
        pass


def card(index, tag, name="Some Card"):
    """Build one offered card, with its tag drawn under it.

    Args:
        index: Which of the three slots the card sits in.
        tag: The Desire tag text, or None for a card carrying none.
        name: The card's name.

    Returns:
        A `(card_dict, boxes)` pair.
    """
    x = CARD_X[index]
    region = (x - 0.0565, CARD_Y + 0.1190, x + 0.1495, CARD_Y + 0.4900)
    boxes = [FakeBox(name, x, CARD_Y - 0.06)]
    if tag is not None:
        boxes.append(FakeBox(tag, (region[0] + region[2]) / 2, (region[1] + region[3]) / 2))
    return {"name": name, "x": x, "y": CARD_Y, "description_region": region}, boxes


def screen(tags, title=REWARD_TITLE, confirm_active=False, priority=()):
    """Build the Desire reward screen and the stubs the handler reads through.

    Args:
        tags: One tag string per card, left to right; None for an untagged card.
        title: The prompt drawn at the top of the screen.
        confirm_active: Whether a card has already been chosen.
        priority: The user's card reward priority list.

    Returns:
        A `(task, utils, handler)` triple.
    """
    cards, boxes = [], [FakeBox(title, 0.5, TITLE_Y)]
    for index, tag in enumerate(tags):
        one, drawn = card(index, tag, name=f"card{index}")
        cards.append(one)
        boxes.extend(drawn)
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
    return task, utils, reward_handler(utils)


class TestBest(unittest.TestCase):
    """Choosing among the offered cards."""

    @staticmethod
    def tagged(*pairs):
        """Build cards carrying tags.

        Args:
            *pairs: One `(name, tags)` pair per card.

        Returns:
            A list of card dicts.
        """
        return [{"name": name, "tags": tags} for name, tags in pairs]

    def test_takes_the_card_carrying_the_target_faction(self):
        cards = self.tagged(("a", {"Control": 1}), ("b", {"Claim": 1}), ("c", {"Inquiry": 1}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_prefers_the_most_points_of_that_faction(self):
        cards = self.tagged(("a", {"Claim": 1}), ("b", {"Claim": 2}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_counts_only_the_target_faction_in_a_merged_tag(self):
        cards = self.tagged(("a", {"Claim": 1, "Control": 2}), ("b", {"Claim": 2}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_falls_back_to_the_priority_list(self):
        cards = self.tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("b", best(cards, "Claim", ["b"])["name"])

    def test_the_priority_list_is_an_order(self):
        cards = self.tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", best(cards, "Claim", ["a", "b"])["name"])

    def test_the_target_faction_outranks_the_priority_list(self):
        # The list ranks cards by their effect; the faction is what the whole run compounds on.
        cards = self.tagged(("a", {"Control": 1}), ("b", {"Claim": 1}))
        self.assertEqual("b", best(cards, "Claim", ["a"])["name"])

    def test_falls_back_to_the_first_card(self):
        cards = self.tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", best(cards, "Claim", [])["name"])

    def test_nothing_offered_is_nothing_chosen(self):
        self.assertIsNone(best([], "Claim", []))


class TestRewardHandler(unittest.TestCase):
    """Claiming the screen."""

    def test_takes_the_card_matching_the_target_faction(self):
        task, _, handler = screen(["[ Control ]", "[ Claim ]", "[ Inquiry ]"])
        self.assertTrue(handler(task))
        self.assertEqual((round(CARD_X[1], 4), round(CARD_Y, 4)), task.clicked)

    def test_settles_after_choosing(self):
        task, _, handler = screen(["[ Claim ]", None, None])
        handler(task)
        self.assertGreater(task.slept, 0)

    def test_stands_aside_once_something_is_chosen(self):
        # Confirm going live is how the screen says a card is selected; the confirm handler takes it there.
        task, _, handler = screen(["[ Claim ]", None, None], confirm_active=True)
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_declines_another_screen(self):
        task, _, handler = screen(["[ Claim ]", None, None], title="Card Reward")
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_reads_the_prompt_without_its_full_stop(self):
        task, _, handler = screen(["[ Claim ]", None, None], title="Select a Desire Card reward")
        self.assertTrue(handler(task))

    def test_takes_an_untagged_card_rather_than_stalling(self):
        # There is no Skip on this screen, so something has to be taken whatever the reader managed to see.
        task, _, handler = screen([None, None, None])
        self.assertTrue(handler(task))
        self.assertEqual((round(CARD_X[0], 4), round(CARD_Y, 4)), task.clicked)

    def test_uses_the_priority_list_when_no_faction_matches(self):
        task, _, handler = screen(["[ Control ]", "[ Inquiry ]", None], priority=["card1"])
        handler(task)
        self.assertEqual((round(CARD_X[1], 4), round(CARD_Y, 4)), task.clicked)


if __name__ == "__main__":
    unittest.main()
