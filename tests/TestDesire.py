"""Check the three screens Season 4's Desire cards arrive on.

Two of them stalled or threw away a run. `Select a Desire Card reward.` offers three cards and has no Skip, and
no handler claimed it, so the run sat on a greyed-out Confirm until the stuck-screen fallback clicked one at
random - close to the worst outcome the mechanic allows, since the faction picked here is what the rest of the
run compounds on. The merge screen's title is `Card Reward`, so the ordinary reward handler claimed it, found
no priority match and pressed Skip, throwing the merge away.

The third is subtler. An event that grants a Desire card opens the ordinary assign screen, and upstream judges
that screen purely on whether the card's name is on the reward priority list. A Desire card's name never is:

    卡牌「It's All Mine」未命中奖励优先级
    无可用刷新或刷新次数，点击跳过非优先级卡牌

All positions here are measured off the runs that hit each screen.
"""

import sys
import types
import unittest
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.desire import (  # noqa: E402
    CARD_PRIORITY, INHERIT_TITLE, PURCHASE_TITLE, REWARD_TITLE, TAKEN, best, inherit_handler,
    keeper, keeping_desire_cards, reward_handler,
)

WIDTH, HEIGHT = 1920, 1080
# Every one of these screens draws its prompt at the same height.
TITLE_Y = 0.145
# The three cards the reward screen offers, measured off the run that stalled on it.
REWARD_X = (0.1927, 0.4661, 0.7396)
REWARD_Y = 0.2713
# The two cards the merge screen offers, measured off the run that met it.
INHERIT_X = (0.2698, 0.6469)
INHERIT_Y = 0.3148
# The granted card's slot on the assign screen, measured off the run that skipped one.
ASSIGN_X, ASSIGN_Y = 0.2151, 0.2731
# Upstream reads the assign card from this band and writes its tag into the description region below it.
DESCRIPTION_REGION = (0.1159, 0.4329, 0.3219, 0.8039)
# Where the Purchase Card screen, which shares the handler, draws its own title.
PURCHASE_POINT = (0.5, 0.13)
# The page label upstream gives its card read. Only a log string, so nothing here may depend on it.
ASSIGN_PAGE = "卡牌分配页面"
# The card a real run was handed, and skipped, twice in four minutes.
NAME = "It's All Mine"


# The Desire screens place their boxes by share of the screen.
FakeBox = partial(Box, width=200, height=30, units="fraction")


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


def tag_region(x, y):
    """Give the description region a card at this position draws its Desire tag in.

    Args:
        x: The card's centre, as a fraction of the screen width.
        y: The card's centre, as a fraction of the screen height.

    Returns:
        A relative `(x1, y1, x2, y2)` box.
    """
    return (x - 0.0565, y + 0.1190, x + 0.1495, y + 0.4900)


def chosen(xs, y, tags, title, confirm_active, priority, build):
    """Build one of the two screens that offer a row of cards, and the stubs its handler reads through.

    Args:
        xs: The card centres, left to right.
        y: The height the cards sit at.
        tags: One tag string per card, left to right; None for a card carrying none.
        title: The prompt drawn at the top of the screen.
        confirm_active: Whether a card has already been chosen.
        priority: The user's card reward priority list.
        build: The handler factory to hand the stubbed `utils` to.

    Returns:
        A `(task, handler)` pair.
    """
    cards, boxes = [], [FakeBox(title, 0.5, TITLE_Y)]
    for index, tag in enumerate(tags):
        x, region, name = xs[index], tag_region(xs[index], y), f"card{index}"
        cards.append({"name": name, "x": x, "y": y, "description_region": region})
        boxes.append(FakeBox(name, x, y - 0.06))
        if tag is not None:
            boxes.append(FakeBox(tag, (region[0] + region[2]) / 2, (region[1] + region[3]) / 2))
    task = FakeTask(boxes)

    def move_and_click(task_, x_, y_):
        task_.clicked = (round(x_, 4), round(y_, 4))

    utils = types.SimpleNamespace(
        recognize_cards=lambda task_, **kwargs: cards,
        find_box_at_point=lambda task_, x_, y_: FakeBox("确认", x_, y_),
        is_button_active=lambda task_, box: confirm_active,
        _move_and_click=move_and_click,
        _get_config_value=lambda task_, key, default: default,
        _get_card_list=lambda task_, key: list(priority),
    )
    return task, build(utils)


def reward_screen(tags, title=REWARD_TITLE, confirm_active=False, priority=()):
    """Build the Desire reward screen.

    Args:
        tags: One tag string per card, left to right; None for a card carrying none.
        title: The prompt drawn at the top of the screen.
        confirm_active: Whether a card has already been chosen.
        priority: The user's card reward priority list.

    Returns:
        A `(task, handler)` pair.
    """
    return chosen(REWARD_X, REWARD_Y, tags, title, confirm_active, priority, reward_handler)


def inherit_screen(tags, title=INHERIT_TITLE, confirm_active=False, priority=()):
    """Build the screen where two Desire cards merge into one.

    Args:
        tags: One tag string per card, left to right.
        title: The prompt drawn at the top of the screen.
        confirm_active: Whether a card has already been picked.
        priority: The user's card reward priority list.

    Returns:
        A `(task, handler)` pair.
    """
    return chosen(INHERIT_X, INHERIT_Y, tags, title, confirm_active, priority, inherit_handler)


def assign_screen(tag, target="Claim", configured=(), purchase=False, page=ASSIGN_PAGE, second=None, taken=None):
    """Build the card assign screen and the stubs the wrapper reads through.

    Args:
        tag: The Desire tag drawn in the card's description, or None for a card carrying none.
        target: The faction the run is chasing.
        configured: The user's own card reward priority list.
        purchase: Whether this is the Purchase Card screen, which shares the handler.
        page: The page label the handler gives its card read, which nothing is allowed to depend on.
        second: A tag for a further card the handler reads after the granted one, or None for no second read.
        taken: The card a Desire screen already chose, or None when the run reached this screen without one.

    Returns:
        A `(task, utils, seen, handler)` quadruple, where `seen` collects what the handler was offered.
    """
    boxes = [FakeBox(NAME, ASSIGN_X, ASSIGN_Y)]
    if tag is not None:
        boxes.append(FakeBox(tag, (DESCRIPTION_REGION[0] + DESCRIPTION_REGION[2]) / 2,
                             (DESCRIPTION_REGION[1] + DESCRIPTION_REGION[3]) / 2))
    if purchase:
        boxes.append(FakeBox(PURCHASE_TITLE, *PURCHASE_POINT))
    task = FakeTask(boxes)
    setattr(task, TAKEN, taken)
    card = {"name": NAME, "x": ASSIGN_X, "y": ASSIGN_Y, "description_region": DESCRIPTION_REGION}
    seen = {}

    later = {"name": "Some Other Card", "x": ASSIGN_X, "y": ASSIGN_Y,
             "description_region": DESCRIPTION_REGION}
    reads = []

    def recognize_cards(task_, region=None, page=None):
        reads.append(page)
        return [later] if len(reads) > 1 else [card]

    def get_config_value(task_, key, default):
        return target if key == "Desire Faction" else default

    def get_card_list(task_, key):
        return list(configured) if key == CARD_PRIORITY else []

    utils = types.SimpleNamespace(recognize_cards=recognize_cards, _get_config_value=get_config_value,
                                  _get_card_list=get_card_list)

    def handler(task_):
        # Upstream's own order: it reads the card first, then the list it judges the card against. Cleared
        # per call, because each call is one frame of a screen that shows until the run answers it.
        reads.clear()
        utils.recognize_cards(task_, region=(0.101, 0.217, 0.291, 0.365), page=page)
        if second is not None:
            boxes.append(FakeBox(second, ASSIGN_X, ASSIGN_Y - 0.1))
            utils.recognize_cards(task_, region=(0.5, 0.2, 0.7, 0.4), page=page)
        seen["offered"] = utils._get_card_list(task_, CARD_PRIORITY)
        return True

    handler.__name__ = "handle_card_assign"
    return task, utils, seen, keeping_desire_cards(handler, utils)


def tagged(*pairs):
    """Build cards carrying tags, for the two scorers.

    Args:
        *pairs: One `(name, tags)` pair per card.

    Returns:
        A list of card dicts.
    """
    return [{"name": name, "tags": tags} for name, tags in pairs]


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# The reward screen


class TestBest(unittest.TestCase):
    """Choosing among the offered cards."""

    def test_takes_the_card_carrying_the_target_faction(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Claim": 1}), ("c", {"Inquiry": 1}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_prefers_the_most_points_of_that_faction(self):
        cards = tagged(("a", {"Claim": 1}), ("b", {"Claim": 2}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_counts_only_the_target_faction_in_a_merged_tag(self):
        cards = tagged(("a", {"Claim": 1, "Control": 2}), ("b", {"Claim": 2}))
        self.assertEqual("b", best(cards, "Claim", [])["name"])

    def test_falls_back_to_the_priority_list(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("b", best(cards, "Claim", ["b"])["name"])

    def test_the_priority_list_is_an_order(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", best(cards, "Claim", ["a", "b"])["name"])

    def test_the_target_faction_outranks_the_priority_list(self):
        # The list ranks cards by their effect; the faction is what the whole run compounds on.
        cards = tagged(("a", {"Control": 1}), ("b", {"Claim": 1}))
        self.assertEqual("b", best(cards, "Claim", ["a"])["name"])

    def test_falls_back_to_the_first_card(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", best(cards, "Claim", [])["name"])

    def test_nothing_offered_is_nothing_chosen(self):
        self.assertIsNone(best([], "Claim", []))


class TestRewardHandler(unittest.TestCase):
    """Claiming the screen."""

    def test_takes_the_card_matching_the_target_faction(self):
        task, handler = reward_screen(["[ Control ]", "[ Claim ]", "[ Inquiry ]"])
        self.assertTrue(handler(task))
        self.assertEqual((round(REWARD_X[1], 4), round(REWARD_Y, 4)), task.clicked)

    def test_settles_after_choosing(self):
        task, handler = reward_screen(["[ Claim ]", None, None])
        handler(task)
        self.assertGreater(task.slept, 0)

    def test_stands_aside_once_something_is_chosen(self):
        # Confirm going live is how the screen says a card is selected; the confirm handler takes it there.
        task, handler = reward_screen(["[ Claim ]", None, None], confirm_active=True)
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_declines_another_screen(self):
        task, handler = reward_screen(["[ Claim ]", None, None], title="Card Reward")
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_reads_the_prompt_without_its_full_stop(self):
        task, handler = reward_screen(["[ Claim ]", None, None], title="Select a Desire Card reward")
        self.assertTrue(handler(task))

    def test_takes_an_untagged_card_rather_than_stalling(self):
        # There is no Skip on this screen, so something has to be taken whatever the reader managed to see.
        task, handler = reward_screen([None, None, None])
        self.assertTrue(handler(task))
        self.assertEqual((round(REWARD_X[0], 4), round(REWARD_Y, 4)), task.clicked)

    def test_the_taken_card_is_remembered_for_the_screen_that_hands_it_over(self):
        # The card assign screen that follows judges on the faction too, and would skip an off-faction pick.
        task, handler = reward_screen(["[ Control ]", "[ Inquiry ]", None])
        handler(task)
        self.assertEqual("card0", getattr(task, TAKEN))

    def test_a_screen_it_declines_remembers_nothing(self):
        task, handler = reward_screen(["[ Claim ]", None, None], title="Card Reward")
        handler(task)
        self.assertIsNone(getattr(task, TAKEN, None))


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# The merge screen


class TestKeeper(unittest.TestCase):
    """Choosing which card carries the merge."""

    def test_the_priority_list_decides(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("b", keeper(cards, ["b"])["name"])

    def test_the_priority_list_is_an_order(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", keeper(cards, ["a", "b"])["name"])

    def test_falls_back_to_the_higher_level_card(self):
        # Both end with the same faction points, so the level is the only thing left worth reading.
        cards = tagged(("a", {"Control": 1}), ("b", {"Control": 1, "Inquiry": 2}))
        self.assertEqual("b", keeper(cards, [])["name"])

    def test_falls_back_to_the_first_card(self):
        cards = tagged(("a", {"Control": 1}), ("b", {"Inquiry": 1}))
        self.assertEqual("a", keeper(cards, [])["name"])

    def test_nothing_offered_is_nothing_chosen(self):
        self.assertIsNone(keeper([], []))


class TestInheritHandler(unittest.TestCase):
    """Claiming the screen."""

    def test_picks_the_card_on_the_priority_list(self):
        task, handler = inherit_screen(["[ Control / Inquiry 2 ]", "[ Inquiry 2 / Control ]"], priority=["card1"])
        self.assertTrue(handler(task))
        self.assertEqual((round(INHERIT_X[1], 4), round(INHERIT_Y, 4)), task.clicked)

    def test_never_skips_the_merge(self):
        # Skipping is what upstream does today, and it throws away points already earned.
        task, handler = inherit_screen(["[ Control ]", "[ Inquiry ]"])
        self.assertTrue(handler(task))
        self.assertIsNotNone(task.clicked)

    def test_stands_aside_once_something_is_picked(self):
        task, handler = inherit_screen(["[ Control ]", "[ Inquiry ]"], confirm_active=True)
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_declines_an_ordinary_card_reward(self):
        # The two screens share a title, so only the prompt tells them apart.
        task, handler = inherit_screen(["[ Control ]", "[ Inquiry ]"], title="Card Reward")
        self.assertFalse(handler(task))
        self.assertIsNone(task.clicked)

    def test_reads_the_prompt_without_its_full_stop(self):
        task, handler = inherit_screen(["[ Control ]", "[ Inquiry ]"],
                                       title="Please select the Desire Card to inherit")
        self.assertTrue(handler(task))


# //////////////////////////////////////////////////////////////////////////////////////////////////
# //////////////////////////////////////////////////////////////////////////////////////////////////
# The assign screen an event hands a card over on


class TestKeepingDesireCards(unittest.TestCase):
    """Offering a granted Desire card to upstream's ladder."""

    def test_a_card_of_the_chased_faction_is_offered(self):
        task, _, seen, handler = assign_screen("Claim]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_the_users_own_list_still_ranks_above_nothing(self):
        task, _, seen, handler = assign_screen("Claim]", configured=["Sever Ties"])
        handler(task)
        self.assertEqual([NAME, "Sever Ties"], seen["offered"])

    def test_a_card_of_another_faction_is_left_to_be_skipped(self):
        # A level spent on a faction the run is not collecting cannot be spent on the one it is.
        task, _, seen, handler = assign_screen("Inquiry]")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_a_levelled_tag_still_counts(self):
        task, _, seen, handler = assign_screen("[ Claim 2 ]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_merged_tag_counts_when_it_carries_the_faction(self):
        task, _, seen, handler = assign_screen("[ Control / Claim 2 ]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_an_ordinary_card_is_left_alone(self):
        task, _, seen, handler = assign_screen(None)
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_effect_text_naming_a_faction_is_not_a_tag(self):
        task, _, seen, handler = assign_screen("Gain Control of a random enemy for 1 turn", target="Control")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_the_purchase_screen_is_left_alone(self):
        # The same handler runs there, and taking a card there spends credits.
        task, _, seen, handler = assign_screen("Claim]", purchase=True)
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_the_handlers_answer_is_passed_through(self):
        task, _, _, handler = assign_screen("Claim]")
        self.assertTrue(handler(task))

    def test_the_page_label_is_not_depended_on(self):
        # It only ever reaches a log, so a rebase is free to rename it and must not bring the bug back.
        task, _, seen, handler = assign_screen("Claim]", page="renamed by some later upstream")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_only_the_first_card_read_is_the_granted_one(self):
        task, _, seen, handler = assign_screen("Claim]", second="Inquiry]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_card_already_chosen_on_a_desire_screen_is_kept(self):
        # The faction was weighed one screen earlier; this screen only hands the card over.
        task, _, seen, handler = assign_screen("Inquiry]", taken=NAME)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_chosen_card_with_no_readable_tag_is_still_kept(self):
        task, _, seen, handler = assign_screen(None, taken=NAME)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_the_pick_survives_a_screen_that_lingers(self):
        # The handler runs once a second for as long as the screen shows, and must answer the same each time.
        task, _, seen, handler = assign_screen("Inquiry]", taken=NAME)
        handler(task)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_pick_for_some_other_card_does_not_carry_over(self):
        task, _, seen, handler = assign_screen("Inquiry]", taken="Some Older Card")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_a_pick_for_some_other_card_is_forgotten(self):
        task, _, _, handler = assign_screen("Inquiry]", taken="Some Older Card")
        handler(task)
        self.assertIsNone(getattr(task, TAKEN))

    def test_a_chosen_card_is_still_not_bought(self):
        task, _, seen, handler = assign_screen("Claim]", purchase=True, taken=NAME)
        handler(task)
        self.assertEqual([], seen["offered"])


if __name__ == "__main__":
    unittest.main()
