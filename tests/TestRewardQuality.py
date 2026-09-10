"""Check what the bot decides is worth buying and keeping."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import rewards  # noqa: E402
from src.en.game_data import COMBATANTS  # noqa: E402
from src.en.overrides import FARMED_COMBATANT  # noqa: E402
from src.en.game_quality import (  # noqa: E402
    CARD_CLASSES, CARD_RARITY, COMBATANT_CLASS, EQUIPMENT_RARITY, EQUIPMENT_SLOT,
)
from src.en.game_quality import COMBATANT_TAG_WEIGHTS, EQUIPMENT_TAGS  # noqa: E402
from src.en.quality import (  # noqa: E402
    CLASS_NAMES, WORTH_TAKING, fold, named, slot_of, suits, team_classes, usable_by, worth_taking,
)

# The shop, twice, exactly as the reader saw it.
SHOP_CARDS = ["Prepare forBattle", "Protectiveshout", "Tactical Action", "Wanderer of theVoid", "Shock"]
SHOP_EQUIPMENT = ["Cloud-WalkingShoes", "Sadism", "TacticalReformation", "Gladiator'sHelmet",
                  "Scout's CombatBoots", "Crimson Sword"]

# The game calls these a Vanguard and two Controllers. "knight" is the data's name for Vanguard.
TEAM = ["Nine", "Orlea", "Tiphera"]

# One Dellang Shop shelf and the Purchase Card screen that confirms buying from it, both exactly as the
# reader saw them in the run that looped between the two for seventy seconds.
LOOPING_SHELF = ["售罄", "Gauntlets of", "Protection", "Reorganize", "Rally", "Big Game Hunter", "技能",
                 "On sale", "200140", "105", "35", "96", "3/3", "免费", "Remaining: 5", "离开"]
LOOPING_PURCHASE = ["购买卡牌", "请选择要接受卡牌的主战员", "无法获得", "攻击力", "Reorganize", "防御力",
                    "技能", "LEVEL", "60", "等级", "[Exhaust ]", "Draw 3", "取消", "购买", "105"]


def unusable_by(classes):
    """Find a card worth buying that the given classes cannot hold.

    Args:
        classes: The team's classes.

    Returns:
        The name of a Legend or Unique card restricted away from them.
    """
    return next(name for name, restricted_to in CARD_CLASSES.items()
                if not set(restricted_to) & classes and CARD_RARITY.get(name) in WORTH_TAKING)


class FakeBox:
    """An OCR box, carrying only the text the reward code reads."""

    def __init__(self, name):
        self.name = name


class FakeTask:
    """A task holding one OCR pass and, once the run has started, the team."""

    def __init__(self, texts, team=None):
        self.all_texts = [FakeBox(text) for text in texts]
        if team is not None:
            setattr(self, rewards.TEAM, team)


class TestRewardQuality(unittest.TestCase):

    def test_the_generated_data_covers_what_a_run_sees(self):
        self.assertGreater(len(CARD_RARITY), 800)
        self.assertGreater(len(EQUIPMENT_RARITY), 400)
        self.assertGreater(len(COMBATANT_CLASS), 40)
        self.assertGreater(len(EQUIPMENT_SLOT), 400)

    def test_a_typographic_apostrophe_still_matches(self):
        """The client writes Gladiator's with a curly apostrophe; nobody types that."""
        self.assertEqual(fold("Gladiator's Helmet"), fold("Gladiator’s Helmet"))

    def test_a_hidden_zero_width_space_still_matches(self):
        """One card name carries an invisible character, which an exact match would never find."""
        self.assertEqual(fold("Sadism"), fold("Sadism​"))

    def test_a_concatenated_reading_still_matches(self):
        """The reader joins words across line breaks, so the spacing cannot be trusted."""
        self.assertEqual(fold("Scout's Combat Boots"), fold("Scout's CombatBoots"))
        self.assertEqual(1, slot_of("Cloud-WalkingShoes"))

    def test_the_team_resolves_to_its_classes(self):
        self.assertEqual({"knight", "controller"}, team_classes(TEAM))

    def test_classes_are_logged_the_way_the_game_names_them(self):
        """The data calls a Vanguard a knight, and a log nobody recognises is worse than no log."""
        self.assertEqual(["Controller", "Vanguard"], named(team_classes(TEAM)))

    def test_every_class_in_the_data_has_an_in_game_name(self):
        """A class added by a future patch must be noticed here, not shipped as a raw id."""
        in_data = set(COMBATANT_CLASS.values()) | {c for cs in CARD_CLASSES.values() for c in cs}
        self.assertEqual(set(), in_data - set(CLASS_NAMES))

    def test_an_unknown_name_leaves_the_team_unknown(self):
        """A misread name must not silently narrow the team and filter out usable cards."""
        self.assertEqual(set(), team_classes(["Nlne", "0rlea"]))

    def test_only_the_best_grades_are_taken(self):
        """Rare is most of what a shop stocks; buying it is how a run ends with nothing."""
        taken = worth_taking(SHOP_CARDS, {"knight", "controller"})
        self.assertEqual(["Prepare for Battle"], taken)
        for name in taken:
            self.assertIn(CARD_RARITY[name], WORTH_TAKING)

    def test_equipment_is_graded_the_same_way(self):
        taken = worth_taking(SHOP_EQUIPMENT, {"knight", "controller"}, cards=False)
        self.assertEqual(["Cloud-Walking Shoes", "Crimson Sword"], taken)

    def test_a_card_no_one_can_hold_is_skipped(self):
        """The one thing the class data is good for: not paying for an unusable Legend."""
        ranger_only = unusable_by({"knight", "controller"})
        self.assertFalse(usable_by(ranger_only, {"knight", "controller"}))
        self.assertEqual([], worth_taking([ranger_only], {"knight", "controller"}))

    def test_an_unknown_team_filters_nothing(self):
        """Better to buy a card nobody can hold than to skip everything because a name was misread."""
        ranger_only = unusable_by({"knight", "controller"})
        self.assertTrue(usable_by(ranger_only, set()))

    def test_the_generated_list_holds_only_what_is_on_screen(self):
        """Offering all 625 good names would invite upstream's loose matching to pair the wrong ones."""
        task = FakeTask(SHOP_CARDS, {"knight", "controller"})
        generated = rewards.generated_list(task, rewards.CARD_KEY)
        self.assertEqual(["Prepare for Battle"], generated)
        self.assertLess(len(generated), 10)

    def test_equipment_is_offered_to_its_own_slot_only(self):
        task = FakeTask(SHOP_EQUIPMENT, {"knight", "controller"})
        by_slot = {slot: rewards.generated_list(task, key) for key, slot in rewards.EQUIPMENT_KEYS.items()}
        self.assertEqual(["Crimson Sword"], by_slot[0])
        self.assertEqual(["Cloud-Walking Shoes"], by_slot[1])
        self.assertEqual([], by_slot[2])

    def test_a_setting_we_do_not_fill_in_is_left_alone(self):
        self.assertIsNone(rewards.generated_list(FakeTask(SHOP_CARDS), "优先移除基础牌"))

    def test_a_configured_list_always_wins(self):
        """The generated list is a fallback, never an override."""
        reader = rewards.filling_in(lambda task, key, default: ["Absolute Zero"], "utils")
        self.assertEqual(["Absolute Zero"],
                         reader(FakeTask(SHOP_CARDS, {"knight"}), rewards.CARD_KEY, []))

    def test_an_empty_list_is_filled_in(self):
        reader = rewards.filling_in(lambda task, key, default: [], "utils")
        self.assertEqual(["Prepare for Battle"],
                         reader(FakeTask(SHOP_CARDS, {"knight", "controller"}), rewards.CARD_KEY, []))

    def test_a_reading_with_no_letters_in_it_matches_nothing(self):
        # One real card is named with three geometric symbols, and folding used to reduce it to an empty
        # string - which every punctuation-only box the reader produces also folds to. A bare "-" was read
        # 310 times in one run, and each one resolved to that card and was offered as a Unique to take.
        for reading in ("-", "+", "•", "」", "?"):
            with self.subTest(reading=reading):
                self.assertEqual([], worth_taking([reading], ()))

    def test_a_card_named_only_in_symbols_still_matches_itself(self):
        # Tiphereth's Archetype payoff card. Dropping it from the index would be the easy fix, but it is a
        # cost-0 Unique and worth taking, so the fold keeps the shapes instead.
        self.assertEqual(["○ △ □"], worth_taking(["○ △ □"], ()))

    def test_nothing_worth_taking_leaves_the_list_empty(self):
        """A shop of Commons must stay a shop of Commons, not become one it buys from."""
        reader = rewards.filling_in(lambda task, key, default: [], "utils")
        self.assertEqual([], reader(FakeTask(["Shock", "Multishot"], {"knight"}), rewards.CARD_KEY, []))


if __name__ == "__main__":
    unittest.main()


class TestPurchaseAgreesWithTheShop(unittest.TestCase):
    """The shop decides to buy, and the screen that confirms the buy has to reach the same answer.

    The shelf and the Purchase Card screen are two views of one decision, judged against the same setting.
    When that setting is filled in from what is on screen, both views have to fill it in the same way. They
    did not: the shelf's handler had the fallback and the purchase screen's did not, so the shop clicked buy,
    the purchase screen found an empty list, cancelled, and the shelf clicked buy again - sixteen times in
    seventy seconds, with nothing detecting it as stuck because the screen kept changing.
    """

    def test_the_purchase_screen_gets_the_fallback_too(self):
        self.assertIn("handle_card_assign", rewards.FILLED_IN)

    def test_both_views_of_one_shelf_pick_the_same_card(self):
        shelf = rewards.generated_list(FakeTask(LOOPING_SHELF, team=set()), rewards.CARD_KEY)
        purchase = rewards.generated_list(FakeTask(LOOPING_PURCHASE, team=set()), rewards.CARD_KEY)
        self.assertEqual(["Reorganize"], shelf)
        self.assertEqual(shelf, purchase)


class TestSuits(unittest.TestCase):
    """Weighing a piece of equipment against the combatant who would wear it.

    The game keeps this opinion for Sortie and leaves the Chaos copies of the same relics blank, so the
    generator carries it across. It covers about a third of what a Chaos run can meet, and a piece with no
    tags has to read as "no opinion" rather than as "unsuitable" - otherwise two thirds of the pool would
    quietly sink below the third that happens to be labelled.
    """

    def test_a_piece_the_combatant_wants_scores_her_own_weight(self):
        # Arabella wants all-attack equipment, and the game says how much.
        self.assertEqual(COMBATANT_TAG_WEIGHTS["Arabella"]["allatk"], suits("Nature's Hostility", "Arabella"))

    def test_a_piece_she_does_not_want_scores_nothing(self):
        self.assertEqual(0, suits("Assault Boots", "Arabella"))

    def test_two_wanted_kinds_on_one_piece_add_up(self):
        weights = COMBATANT_TAG_WEIGHTS["Nia"]
        self.assertEqual(weights["discard"] + weights["draw"],
                         suits("Fragment of the Empty Void", "Nia"))

    def test_an_untagged_piece_is_no_opinion(self):
        # Not a named piece: coverage grows with every dump, and the test should outlive any one item.
        untagged = next(name for name in EQUIPMENT_RARITY if name not in EQUIPMENT_TAGS)
        self.assertEqual(0, suits(untagged, "Arabella"))

    def test_a_combatant_the_data_does_not_know_has_no_opinion(self):
        self.assertEqual(0, suits("Nature's Hostility", "Someone Unreleased"))

    def test_a_reading_that_is_not_equipment_scores_nothing(self):
        self.assertEqual(0, suits("Rewards cannot be obtained", "Arabella"))

    def test_a_concatenated_reading_still_matches(self):
        # The reader runs words together constantly - "Gauntlets ofProtection" is from a real run.
        self.assertEqual(suits("Fragment of the Empty Void", "Nia"),
                         suits("Fragment of theEmpty Void", "Nia"))

    def test_every_released_combatant_has_an_opinion(self):
        # A dump that stopped carrying these would leave the shopping list ordered by name again, silently.
        self.assertEqual(set(), set(COMBATANTS) - set(COMBATANT_TAG_WEIGHTS))


class TestWorthTakingSuited(unittest.TestCase):
    """Ordering the generated shopping list by who is going to wear the thing."""

    SHELF = ["Nature's Hostility", "Assault Boots", "Blood Giant Claw"]

    def test_the_wanted_piece_comes_first(self):
        # Compared folded: the client spells this one with a typographic apostrophe.
        first = worth_taking(self.SHELF, cards=False, suited_to="Arabella")[0]
        self.assertEqual(fold("Nature's Hostility"), fold(first))

    def test_without_a_combatant_the_order_is_unchanged(self):
        self.assertEqual(worth_taking(self.SHELF, cards=False),
                         worth_taking(self.SHELF, cards=False, suited_to=None))

    def test_rarity_still_outranks_the_preference(self):
        # A Legend she wants must not jump a Unique she does not: the run wants the better item.
        shelf = ["Nature's Hostility", "Fragment of the Empty Void"]
        self.assertEqual("Fragment of the Empty Void",
                         worth_taking(shelf, cards=False, suited_to="Arabella")[0])

    def test_an_unknown_combatant_changes_nothing(self):
        self.assertEqual(worth_taking(self.SHELF, cards=False),
                         worth_taking(self.SHELF, cards=False, suited_to="Someone Unreleased"))

    def test_cards_are_untouched_by_it(self):
        self.assertEqual(worth_taking(SHOP_CARDS), worth_taking(SHOP_CARDS, suited_to="Arabella"))


class TestFarmedCombatantReachesTheList(unittest.TestCase):
    """The farming target reaches the shopping list, read through the reader being stood in for.

    Reading it around that reader would be the easy mistake: this code runs as the stand-in for it, so asking
    through the module attribute would come straight back here. It also has to survive the slot filter, which
    is the only thing this layer adds over `worth_taking`.
    """

    # Two slot-0 Legends: the game says Arabella wants the first kind and says nothing about the second.
    SHELF = ["Nature's Hostility", "Blood Giant Claw"]
    SLOT_ONE = next(key for key, slot in rewards.EQUIPMENT_KEYS.items() if slot == 0)

    def offered(self, config):
        """Read back what the list offers for the first equipment slot.

        Args:
            config: The settings the run is holding, as the reader would answer them.

        Returns:
            The names offered, best first.
        """
        reader = rewards.filling_in(lambda task, key, default: config.get(key, default), "utils")
        return reader(FakeTask(self.SHELF), self.SLOT_ONE, [])

    def test_the_configured_combatant_orders_the_equipment(self):
        self.assertEqual(fold("Nature's Hostility"), fold(self.offered({FARMED_COMBATANT: "Arabella"})[0]))

    def test_an_unset_combatant_leaves_the_name_order_alone(self):
        self.assertEqual(fold("Blood Giant Claw"), fold(self.offered({})[0]))

    def test_only_this_slot_is_offered(self):
        self.assertEqual(2, len(self.offered({FARMED_COMBATANT: "Arabella"})))
