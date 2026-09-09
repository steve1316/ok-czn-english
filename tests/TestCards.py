"""Check which card the picker plays, and in what order.

Real card names throughout, so a reading that stops agreeing with the client's own data fails here rather
than in a run. `Anchor` and `Annihilation Shot` are the same card in every respect the picker reads - one
Action Point, an Attack, exactly "100% Damage" - except that Haru is Justice and Renoa is Void. That makes
them the fair pair for anything about attributes.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import cards  # noqa: E402

JUSTICE_ATTACK = "Anchor"
VOID_ATTACK = "Annihilation Shot"
# Costs nothing, so only the Curse rule can keep it out of a plan.
CURSE = "Anemia"
# Costs nothing and even draws a card, and is still never worth playing.
AILMENT = "Anxiety"
# Free, and draws.
FREE_DRAW = "Adagio"
# One Action Point, and a Power card.
BUFF = "Arcane Rush"
# Free, and an Attack, so it separates "free first" from "setup first".
FREE_ATTACK = "Magnum Shot"
# Two Action Points for 220% damage, which is better value per point than 100% for one.
BIG_ATTACK = "Charge Launcher"
# Spends every Action Point left rather than a fixed number.
SPENDS_EVERYTHING = "Absolute Protection"


def hand(*names_in_order):
    """Build a hand the way `_hand_cards` hands one over.

    Args:
        names_in_order: Card names, left to right as they sit on screen.

    Returns:
        A list of hand-card dicts, each carrying the hotkey that plays it.
    """
    return [{"name": name, "key": str(index + 1)} for index, name in enumerate(names_in_order)]


def played(chosen):
    """Reduce a plan to the names it plays, in order.

    Args:
        chosen: The plan.

    Returns:
        The card names.
    """
    return [card["name"] for card in chosen]


class TestNeverPlayed(unittest.TestCase):
    """Cards the game deals you rather than ones you choose."""

    def test_a_curse_is_left_in_hand(self):
        self.assertNotIn(CURSE, played(cards.plan(hand(CURSE, JUSTICE_ATTACK), cards.Board())))

    def test_a_status_ailment_is_left_in_hand(self):
        self.assertNotIn(AILMENT, played(cards.plan(hand(AILMENT, JUSTICE_ATTACK), cards.Board())))

    def test_a_hand_of_nothing_but_junk_plays_nothing(self):
        self.assertEqual(cards.plan(hand(CURSE, AILMENT), cards.Board()), [])


class TestAffordability(unittest.TestCase):
    """The Action Point budget, which upstream never knew anything about."""

    def test_a_plan_stays_inside_the_budget(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK, BUFF), cards.Board(action_points=2))
        spent = sum(cards.cost(card["name"]) for card in chosen)
        self.assertLessEqual(spent, 2)

    def test_a_free_card_is_played_whatever_the_budget(self):
        self.assertEqual(played(cards.plan(hand(FREE_DRAW), cards.Board(action_points=0))), [FREE_DRAW])

    def test_nothing_affordable_plays_nothing(self):
        self.assertEqual(cards.plan(hand(JUSTICE_ATTACK), cards.Board(action_points=0)), [])


class TestOrdering(unittest.TestCase):
    """The order a turn is played in, which is most of what separates good play from legal play."""

    def test_a_free_card_goes_before_one_that_costs_anything(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, FREE_ATTACK), cards.Board())
        self.assertEqual(played(chosen)[0], FREE_ATTACK)

    def test_a_buff_goes_before_an_attack(self):
        # Both cost one, so only the rule that a Power card should land before the attack it improves can
        # decide this.
        chosen = cards.plan(hand(JUSTICE_ATTACK, BUFF), cards.Board())
        self.assertEqual(played(chosen), [BUFF, JUSTICE_ATTACK])

    def test_the_better_value_attack_goes_first(self):
        # 220% for two points beats 100% for one, and three points pays for both.
        chosen = cards.plan(hand(JUSTICE_ATTACK, BIG_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [BIG_ATTACK, JUSTICE_ATTACK])

    def test_a_cheap_card_does_not_crowd_out_a_better_one(self):
        # Spending a point on the buff would leave nothing for the two-point attack. Which cards get played
        # has to be settled on what they are worth, and only then put in the order they are played in.
        chosen = cards.plan(hand(BUFF, BIG_ATTACK), cards.Board(action_points=2))
        self.assertEqual(played(chosen), [BIG_ATTACK])

    def test_a_tight_budget_buys_the_better_attack(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, BIG_ATTACK), cards.Board(action_points=2))
        self.assertEqual(played(chosen), [BIG_ATTACK])


class TestSpendsEverything(unittest.TestCase):
    """A card with no fixed price takes whatever is left, so it can only ever be played last."""

    def test_it_goes_after_a_card_with_a_price(self):
        chosen = cards.plan(hand(SPENDS_EVERYTHING, JUSTICE_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, SPENDS_EVERYTHING])

    def test_nothing_is_played_after_it(self):
        # Four points, so the two attacks costing three between them still leave it something to spend.
        chosen = cards.plan(hand(SPENDS_EVERYTHING, JUSTICE_ATTACK, BIG_ATTACK), cards.Board(action_points=4))
        self.assertEqual(played(chosen)[-1], SPENDS_EVERYTHING)

    def test_it_is_not_played_with_no_points_left(self):
        chosen = cards.plan(hand(SPENDS_EVERYTHING), cards.Board(action_points=0))
        self.assertEqual(chosen, [])


class TestWeakness(unittest.TestCase):
    """Matching the attribute an enemy is weak to, which is where most free damage in this game comes from."""

    def test_the_matching_attribute_goes_first(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board(weakness="Void"))
        self.assertEqual(played(chosen), [VOID_ATTACK, JUSTICE_ATTACK])

    def test_an_unknown_weakness_leaves_the_order_alone(self):
        # Nothing separates these two without a weakness to match, so the hand's own order has to survive.
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, VOID_ATTACK])

    def test_a_weakness_nobody_matches_leaves_the_order_alone(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board(weakness="Passion"))
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, VOID_ATTACK])


class TestEpiphany(unittest.TestCase):
    """A glowing card upgrades itself when played, which is worth more than one turn of damage."""

    def test_the_glowing_card_goes_first(self):
        chosen = cards.plan(hand(BIG_ATTACK, JUSTICE_ATTACK), cards.Board(epiphany=JUSTICE_ATTACK))
        self.assertEqual(played(chosen)[0], JUSTICE_ATTACK)

    def test_the_glowing_card_is_bought_before_a_bigger_one(self):
        # Two points buys either the 220% attack or the glowing one. The Epiphany is a permanent upgrade, so
        # it is worth more than the turn of damage it gives up.
        board = cards.Board(action_points=2, epiphany=JUSTICE_ATTACK)
        chosen = cards.plan(hand(BIG_ATTACK, JUSTICE_ATTACK), board)
        self.assertEqual(played(chosen), [JUSTICE_ATTACK])

    def test_a_glowing_curse_is_still_never_played(self):
        chosen = cards.plan(hand(CURSE, JUSTICE_ATTACK), cards.Board(epiphany=CURSE))
        self.assertNotIn(CURSE, played(chosen))


class TestTellingCardsFromLabels(unittest.TestCase):
    """The game prints a type label under every card, and the reader hands both back the same way."""

    def test_a_real_card_is_a_card(self):
        self.assertTrue(cards.is_card_name("Anchor"))

    def test_a_type_label_is_not_a_card(self):
        for label in ("Basic Attack", "Basic Skill", "Status Ailment", "Skill", "Attack"):
            with self.subTest(label=label):
                self.assertFalse(cards.is_card_name(label))

    def test_a_truncated_type_label_is_not_a_card(self):
        # "Basic Atta" was the single most common junk reading in a real Chaos recording.
        for stub in ("Basic Atta", "Status Ailm", "XBasic A", "Basic"):
            with self.subTest(stub=stub):
                self.assertFalse(cards.is_card_name(stub))

    def test_the_chinese_label_the_catalog_rewrites_to_is_not_a_card(self):
        # `ocr.po` turns "Defense" into this, and upstream's own exclude list has no defense keyword, so it
        # reached the hand as a card name 22 times in one recording.
        self.assertFalse(cards.is_card_name("防御力"))

    def test_a_card_whose_name_starts_with_a_label_is_still_a_card(self):
        # These are the ones a careless label test deletes. Each is a real card whose name begins with a type
        # label, so the known-card check has to run before the truncation test.
        for name in ("Curse of the Fairy", "Defense System", "Power Anchor", "Attack, My Minions"):
            with self.subTest(card=name):
                self.assertTrue(cards.is_card_name(name))

    def test_a_card_named_exactly_after_a_label_loses_to_the_label(self):
        # Only two cards collide this way and `ocr.po` already decided it: the label sits under every card of
        # its type, the card is one of 794. `Curse` costs nothing since curse cards are never played anyway.
        self.assertFalse(cards.is_card_name("Attack!"))
        self.assertFalse(cards.is_card_name("Curse"))

    def test_a_card_released_after_the_dump_is_still_a_card(self):
        self.assertTrue(cards.is_card_name("Some Card From A Later Patch"))


class TestReadingNames(unittest.TestCase):
    """What the reader hands over is rarely spelt the way the data spells it."""

    def test_a_name_run_together_is_still_recognised(self):
        chosen = cards.plan(hand("AnnihilationShot"), cards.Board())
        self.assertEqual(cards.cost("AnnihilationShot"), cards.cost(VOID_ATTACK))
        self.assertEqual(len(chosen), 1)

    def test_case_and_spacing_do_not_matter(self):
        self.assertEqual(cards.canonical("  anchor "), JUSTICE_ATTACK)

    def test_a_hotkey_run_into_the_name_is_stripped(self):
        # The hotkey is printed just above the card, close enough that the reader sometimes returns the two
        # as one box. A real Sortie hand came back with "1=Soul Riff" beside four cleanly read names.
        self.assertEqual(cards.canonical("1=Soul Riff"), "Soul Riff")

    def test_a_name_cut_short_is_repaired(self):
        # The reader truncates a name mid-word while the hand animates. "Knife Tos" was read 10 times in one
        # Chaos recording, and it can only ever have been one card.
        self.assertEqual(cards.canonical("Knife Tos"), "Knife Toss")

    def test_an_ambiguous_stub_is_left_alone(self):
        # Two cards start this way, so guessing between them would be worse than not knowing.
        self.assertEqual(cards.canonical("Attac"), "Attac")

    def test_a_stub_too_short_to_be_sure_is_left_alone(self):
        self.assertEqual(cards.canonical("Bas"), "Bas")

    def test_a_card_the_data_never_heard_of_is_still_played(self):
        chosen = cards.plan(hand("Some Card From A Later Patch"), cards.Board())
        self.assertEqual(len(chosen), 1)

    def test_an_unreadable_card_does_not_stop_the_rest_of_the_turn(self):
        chosen = cards.plan(hand("", JUSTICE_ATTACK), cards.Board())
        self.assertIn(JUSTICE_ATTACK, played(chosen))


if __name__ == "__main__":
    unittest.main()
