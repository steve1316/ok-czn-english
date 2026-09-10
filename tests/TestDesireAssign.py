"""Check that a Desire card handed out by an event is kept rather than skipped.

An event that grants a Desire card does not open either of the Desire screens. It opens the ordinary card
assign screen - `Card Reward` over `Please select the combatant to receive the card` - with the granted card
sitting alone on the left, its faction tag drawn in the description. Upstream decides that screen purely on
whether the card's name is on the user's reward priority list, and a Desire card's name never is, so the run
presses Skip and the faction points the event just paid for are thrown away.

From a real run, twice in four minutes, with the faction being chased set to Claim:

    卡牌分配页面: 卡牌1: 名称=「It's All Mine」，描述=「200%DamageClaim]Defeat: 1 Morale ...」
    卡牌「It's All Mine」未命中奖励优先级
    无可用刷新或刷新次数，点击跳过非优先级卡牌

The card is offered to upstream's own ladder as a priority hit instead, which then assigns it - and already
prefers the save-data combatant when doing so. Only the faction being chased earns that: a card of another
faction fills one of a combatant's three Desire levels with points the run is not collecting, and those
levels are scarcer than the cards are.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.desire import CARD_PRIORITY, PURCHASE_TITLE, TAKEN, keeping_desire_cards  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
# The granted card's slot, measured off the run that skipped one.
CARD_X, CARD_Y = 0.2151, 0.2731
# Upstream reads the card from this band, and writes its tag into the description region below it.
DESCRIPTION_REGION = (0.1159, 0.4329, 0.3219, 0.8039)
# Where the Purchase Card screen draws its own title.
PURCHASE_POINT = (0.5, 0.13)
# The page label upstream gives its card read. Only a log string, so nothing here may depend on it.
ASSIGN_PAGE = "卡牌分配页面"
# The card a real run was handed, and skipped, twice.
NAME = "It's All Mine"


class FakeBox:
    """An OCR box positioned by its centre."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 200, 30
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


class FakeTask:
    """A task holding one OCR pass of the card assign screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes


def screen(tag, target="Claim", configured=(), purchase=False, page=ASSIGN_PAGE, second=None, taken=None):
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
    boxes = [FakeBox(NAME, CARD_X, CARD_Y)]
    if tag is not None:
        boxes.append(FakeBox(tag, (DESCRIPTION_REGION[0] + DESCRIPTION_REGION[2]) / 2,
                             (DESCRIPTION_REGION[1] + DESCRIPTION_REGION[3]) / 2))
    if purchase:
        boxes.append(FakeBox(PURCHASE_TITLE, *PURCHASE_POINT))
    task = FakeTask(boxes)
    setattr(task, TAKEN, taken)
    card = {"name": NAME, "x": CARD_X, "y": CARD_Y, "description_region": DESCRIPTION_REGION}
    seen = {}

    later = {"name": "Some Other Card", "x": CARD_X, "y": CARD_Y,
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
            boxes.append(FakeBox(second, CARD_X, CARD_Y - 0.1))
            utils.recognize_cards(task_, region=(0.5, 0.2, 0.7, 0.4), page=page)
        seen["offered"] = utils._get_card_list(task_, CARD_PRIORITY)
        return True

    handler.__name__ = "handle_card_assign"
    return task, utils, seen, keeping_desire_cards(handler, utils)


class TestKeepingDesireCards(unittest.TestCase):
    """Offering a granted Desire card to upstream's ladder."""

    def test_a_card_of_the_chased_faction_is_offered(self):
        task, _, seen, handler = screen("Claim]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_the_users_own_list_still_ranks_above_nothing(self):
        task, _, seen, handler = screen("Claim]", configured=["Sever Ties"])
        handler(task)
        self.assertEqual([NAME, "Sever Ties"], seen["offered"])

    def test_a_card_of_another_faction_is_left_to_be_skipped(self):
        # A level spent on a faction the run is not collecting cannot be spent on the one it is.
        task, _, seen, handler = screen("Inquiry]")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_a_levelled_tag_still_counts(self):
        task, _, seen, handler = screen("[ Claim 2 ]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_merged_tag_counts_when_it_carries_the_faction(self):
        task, _, seen, handler = screen("[ Control / Claim 2 ]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_an_ordinary_card_is_left_alone(self):
        task, _, seen, handler = screen(None)
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_effect_text_naming_a_faction_is_not_a_tag(self):
        task, _, seen, handler = screen("Gain Control of a random enemy for 1 turn", target="Control")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_the_purchase_screen_is_left_alone(self):
        # The same handler runs there, and taking a card there spends credits.
        task, _, seen, handler = screen("Claim]", purchase=True)
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_the_stubs_are_put_back(self):
        task, utils, _, handler = screen("Claim]")
        before = (utils.recognize_cards, utils._get_card_list)
        handler(task)
        self.assertEqual(before, (utils.recognize_cards, utils._get_card_list))

    def test_the_handlers_answer_is_passed_through(self):
        task, _, _, handler = screen("Claim]")
        self.assertTrue(handler(task))

    def test_the_page_label_is_not_depended_on(self):
        # It only ever reaches a log, so a rebase is free to rename it and must not bring the bug back.
        task, _, seen, handler = screen("Claim]", page="renamed by some later upstream")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_only_the_first_card_read_is_the_granted_one(self):
        task, _, seen, handler = screen("Claim]", second="Inquiry]")
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_card_already_chosen_on_a_desire_screen_is_kept(self):
        # The faction was weighed one screen earlier; this screen only hands the card over.
        task, _, seen, handler = screen("Inquiry]", taken=NAME)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_chosen_card_with_no_readable_tag_is_still_kept(self):
        task, _, seen, handler = screen(None, taken=NAME)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_the_pick_survives_a_screen_that_lingers(self):
        # The handler runs once a second for as long as the screen shows, and must answer the same each time.
        task, _, seen, handler = screen("Inquiry]", taken=NAME)
        handler(task)
        handler(task)
        self.assertEqual([NAME], seen["offered"])

    def test_a_pick_for_some_other_card_does_not_carry_over(self):
        task, _, seen, handler = screen("Inquiry]", taken="Some Older Card")
        handler(task)
        self.assertEqual([], seen["offered"])

    def test_a_pick_for_some_other_card_is_forgotten(self):
        task, _, _, handler = screen("Inquiry]", taken="Some Older Card")
        handler(task)
        self.assertIsNone(getattr(task, TAKEN))

    def test_a_chosen_card_is_still_not_bought(self):
        task, _, seen, handler = screen("Claim]", purchase=True, taken=NAME)
        handler(task)
        self.assertEqual([], seen["offered"])


if __name__ == "__main__":
    unittest.main()
