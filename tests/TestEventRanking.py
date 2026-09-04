"""Check which event option the bot decides to take.

`src/en/events.py` changes two of upstream's decisions, and both are easy to get subtly wrong. Ranking has to
survive OCR that concatenates an option's boxes in an unpredictable order, and the option that ends the event
has to be withheld while anything else is on offer - a logged Chaos run shows upstream choosing it five times.

Every description here was captured from the 2026-09-04 Chaos run, mangling and all. Nothing is invented.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.events import (  # noqa: E402
    ATTACK, ATTACK_RANK, MIN_LATIN_MARKER_LENGTH, MIN_MARKER_LENGTH, QUIT, QUIT_RANK, REWARD_RANK,
    SPARK, SPARK_RANK,
    drop_quit, fold, order, rank,
)

# Real descriptions, with the tier each must land in.
REAL_OPTIONS = {
    # Spark. The client writes this several ways and OCR loses spaces at line breaks.
    "Bury the bodySpark an Epiphany for arandom Combatant 1 time(s)": SPARK_RANK,
    "[Dexterous] Help with the workDice Roll 14Upon success Spark a DivineEpiphany to 1 random card(s)": SPARK_RANK,
    "Extract the essenceA selected combatant gainsEpiphany 1 time, Forcefullyobtain Curse Card(s) [Paras": SPARK_RANK,
    # Rewards.
    "Gather salvageIncrease Credits by 140": REWARD_RANK,
    "Activate WaypointObtain Equipment [AssaultGauntlets]": REWARD_RANK,
    "Examine the rootRecover Health by 40%,Decrease all Combatants'Stress by 6": REWARD_RANK,
    "Carve the wordsSelect and obtain 1 among 3random Neutral Rare Card.": REWARD_RANK,
    "Taste the mushroomIncrease max Health by 10%": REWARD_RANK,
    # Combat.
    "Enter InsideEvent Encounter: Inside theBrood Lord": ATTACK_RANK,
    "Enter through the gateEvent encounter: Inside theTreasure Trove": ATTACK_RANK,
    # Quit. The catalog rewrites the title box to Chinese and OCR mangles the other phrasing four ways.
    "离开End the event": QUIT_RANK,
    "I'll let you live.End the event": QUIT_RANK,
    "II et you live.End the event": QUIT_RANK,
    'I"I let you live.End the event': QUIT_RANK,
}

# The same option, captured twice with its OCR boxes joined in a different order.
SCRAMBLED_PAIRS = [
    ("Bury the bodySpark an Epiphany for arandom Combatant 1 time(s)",
     "Bury the bodyrandom Combatant 1 time(s)Spark an Epiphany for a"),
    ("Examine the rootRecover Health by 40%,Decrease all Combatants'Stress by 6",
     "Examine the rootRecover Health by 40%,Stress by 6Decrease all Combatants'"),
    ("Enter InsideEvent Encounter: Inside theBrood Lord",
     "Enter InsideBrood LordEvent Encounter: Inside the"),
]


def option(description, y=0.95):
    """Build an option dict the shape `recognize_event_options` produces.

    Args:
        description: The option text.
        y: Its centre height, which upstream's upper-half shortcut keys off.

    Returns:
        The option dict.
    """
    return {"description": description, "x": 0.5, "y": y,
            "description_region": (0.4, 0.8, 0.6, 0.9), "feature_name": "event1", "confidence": 0.99}


def is_subsequence(first, second):
    """Upstream's matcher for the user's own keywords, copied so the test needs no game code.

    Args:
        first: The configured keyword.
        second: The option description.

    Returns:
        True when every character of the keyword appears in order.
    """
    second_iter = iter(second)
    return all(char in second_iter for char in first)


class TestEventRanking(unittest.TestCase):

    def test_real_options_land_in_the_right_tier(self):
        for description, expected in REAL_OPTIONS.items():
            with self.subTest(description=description[:48]):
                self.assertEqual(expected, rank(description))

    def test_box_order_does_not_change_the_answer(self):
        """OCR joins an option's boxes in an unstable order, so ranking must not depend on position."""
        for first, second in SCRAMBLED_PAIRS:
            with self.subTest(option=first[:40]):
                self.assertEqual(rank(first), rank(second))

    def test_a_lost_space_does_not_hide_a_marker(self):
        """The reader drops spaces at line breaks, which a plain substring test would miss."""
        self.assertEqual(SPARK_RANK, rank("Sparka DivineEpiphany"))
        self.assertEqual(SPARK_RANK, rank("Spark an Epiphanyfor a"))

    def test_every_marker_survives_folding(self):
        """A marker that folded away to nothing would be `in` every description and match everything."""
        for marker in SPARK + QUIT + ATTACK:
            with self.subTest(marker=marker):
                self.assertGreaterEqual(len(fold(marker)), MIN_MARKER_LENGTH)

    def test_latin_markers_are_whole_phrases(self):
        """Two Chinese characters are a specific word; two Latin letters would match half the screen."""
        for marker in SPARK + QUIT + ATTACK:
            if marker.isascii():
                with self.subTest(marker=marker):
                    self.assertGreaterEqual(len(fold(marker)), MIN_LATIN_MARKER_LENGTH)

    def test_a_catalog_rewritten_box_still_ranks(self):
        """A box reading exactly "Epiphany" is rewritten to Chinese before the description is assembled."""
        self.assertEqual(SPARK_RANK, rank("Bury the body闪光for a random Combatant"))

    def test_quit_is_withheld_while_anything_else_is_offered(self):
        """The whole point: upstream took the end-the-event option five times in one logged run."""
        for other in ("Gather salvageIncrease Credits by 140",
                      "Enter InsideEvent Encounter: Inside theBrood Lord",
                      "Bury the bodySpark an Epiphany for arandom Combatant 1 time(s)"):
            with self.subTest(other=other[:40]):
                kept = drop_quit([option("离开End the event"), option(other)])
                self.assertEqual([other], [o["description"] for o in kept])

    def test_quit_survives_when_it_is_the_only_option(self):
        """Withholding the last option would leave the bot with nothing to click."""
        only = [option("离开End the event")]
        self.assertEqual(only, drop_quit(only))

    def test_every_quit_phrasing_is_withheld(self):
        quits = [option(text) for text, tier in REAL_OPTIONS.items() if tier == QUIT_RANK]
        kept = drop_quit(quits + [option("Gather salvageIncrease Credits by 140")])
        self.assertEqual(1, len(kept))

    def test_ordering_puts_the_best_option_first(self):
        """Upstream's upper-half shortcut takes the first option it can, so first must mean best."""
        options = [option("Enter InsideEvent Encounter: Inside theBrood Lord"),
                   option("Gather salvageIncrease Credits by 140"),
                   option("Bury the bodySpark an Epiphany for arandom Combatant 1 time(s)")]
        ordered = order(options, [], is_subsequence)
        self.assertEqual(SPARK_RANK, rank(ordered[0]["description"]))
        self.assertEqual(ATTACK_RANK, rank(ordered[-1]["description"]))

    def test_a_configured_priority_beats_the_ranking(self):
        """The user's own list is upstream's contract and must still win, ahead of any tier."""
        options = [option("Bury the bodySpark an Epiphany for arandom Combatant 1 time(s)"),
                   option("Gather salvageIncrease Credits by 140")]
        ordered = order(options, ["Credits"], is_subsequence)
        self.assertIn("Credits by 140", ordered[0]["description"])

    def test_configured_priorities_keep_their_configured_order(self):
        options = [option("Activate WaypointObtain Equipment [AssaultGauntlets]"),
                   option("Gather salvageIncrease Credits by 140")]
        ordered = order(options, ["Credits", "Equipment"], is_subsequence)
        self.assertIn("Credits by 140", ordered[0]["description"])

    def test_equal_options_keep_their_original_order(self):
        """A stable sort keeps the ordering upstream gave us, which is left to right on screen."""
        options = [option("Gather salvageIncrease Credits by 140"),
                   option("Taste the mushroomIncrease max Health by 10%")]
        self.assertEqual([o["description"] for o in options],
                         [o["description"] for o in order(options, [], is_subsequence)])


if __name__ == "__main__":
    unittest.main()
