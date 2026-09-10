"""Check what the bot decides is worth buying and keeping."""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import rewards  # noqa: E402
from src.en.game_quality import (  # noqa: E402
    CARD_CLASSES, CARD_RARITY, COMBATANT_CLASS, EQUIPMENT_RARITY, EQUIPMENT_SLOT,
)
from src.en.quality import (  # noqa: E402
    CLASS_NAMES, WORTH_TAKING, fold, named, slot_of, team_classes, usable_by, worth_taking,
)

# The shop, twice, exactly as the reader saw it.
SHOP_CARDS = ["Prepare forBattle", "Protectiveshout", "Tactical Action", "Wanderer of theVoid", "Shock"]
SHOP_EQUIPMENT = ["Cloud-WalkingShoes", "Sadism", "TacticalReformation", "Gladiator'sHelmet",
                  "Scout's CombatBoots", "Crimson Sword"]

# The game calls these a Vanguard and two Controllers. "knight" is the data's name for Vanguard.
TEAM = ["Nine", "Orlea", "Tiphera"]


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
