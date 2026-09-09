"""Check what can be reconstructed from a recording of the game's own Auto AI playing a battle.

The recorder writes down hands, not decisions. Everything about what Auto actually played is inferred here,
so these tests are where the inference is held honest - and every case below is one that really happened in
a live run rather than one invented for the test.
"""

import sys
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import autoplay  # noqa: E402

# Real card names, so canonical folding is exercised rather than bypassed.
ATTACK = "Anchor"
BIG_ATTACK = "Charge Launcher"
DRAWER = "Prepare to Subdue"
HEAL = "Amp Therapy"


def frame(names, count=None, points=True, weakness=None, at=0.0):
    """Build one recorded frame the way the recorder writes it.

    Args:
        names: Card names in hand, left to right.
        count: The hand count readout, defaulting to the length of `names`.
        points: Whether the Action Point readout was lit.
        weakness: The attribute the enemies shared, or None.
        at: The frame timestamp.

    Returns:
        A `Frame`.
    """
    hand = tuple((name, str(index + 1)) for index, name in enumerate(names))
    return autoplay.Frame(at=at, hand=hand, count=len(names) if count is None else count,
                          points=points, weakness=weakness, egos=(), enemies=1)


class TestDepartures(unittest.TestCase):
    """What left the hand between two frames."""

    def test_one_card_leaving_is_one_departure(self):
        self.assertEqual(autoplay.departures(frame([ATTACK, BIG_ATTACK]), frame([BIG_ATTACK])),
                         Counter({ATTACK: 1}))

    def test_one_copy_of_three_leaving_is_one_departure(self):
        # A hand of three of a card going to two has lost one copy, not the name. Reading this as "the name
        # is still there, so nothing was played" is the bug that stranded cards in a live Sortie run.
        before = frame([ATTACK, ATTACK, ATTACK])
        after = frame([ATTACK, ATTACK])
        self.assertEqual(autoplay.departures(before, after), Counter({ATTACK: 1}))

    def test_a_card_arriving_is_not_a_departure(self):
        self.assertEqual(autoplay.departures(frame([ATTACK]), frame([ATTACK, BIG_ATTACK])), Counter())

    def test_an_ocr_variant_of_the_same_name_is_not_a_departure(self):
        # "NA:Attack Response" and "NA: Attack Response" both came back from the reader in one run, and a
        # spacing difference must not read as one card leaving and another arriving.
        self.assertEqual(autoplay.departures(frame(["Amp Therapy"]), frame(["AmpTherapy"])), Counter())


class TestDecisions(unittest.TestCase):
    """The per-decision labels, which are only taken where exactly one card left."""

    def test_a_single_departure_is_a_labelled_decision(self):
        found = autoplay.decisions([frame([ATTACK, BIG_ATTACK]), frame([BIG_ATTACK])])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].played, ATTACK)
        self.assertEqual(found[0].hand, (ATTACK, BIG_ATTACK))

    def test_two_departures_are_not_labelled(self):
        # Auto outran the sampling rate, so which of the two it chose first is unknowable.
        self.assertEqual(autoplay.decisions([frame([ATTACK, BIG_ATTACK, HEAL]), frame([HEAL])]), [])

    def test_a_card_that_drew_two_more_is_still_one_decision(self):
        found = autoplay.decisions([frame([DRAWER, ATTACK]), frame([ATTACK, HEAL, BIG_ATTACK])])
        self.assertEqual([decision.played for decision in found], [DRAWER])

    def test_nothing_leaving_is_not_a_decision(self):
        self.assertEqual(autoplay.decisions([frame([ATTACK]), frame([ATTACK])]), [])

    def test_no_decision_is_taken_across_a_new_turn(self):
        # The hand grows when it is dealt again, and the discard that precedes it is not a play.
        self.assertEqual(autoplay.decisions([frame([ATTACK]), frame([BIG_ATTACK, HEAL, DRAWER])]), [])

    def test_the_board_state_travels_with_the_decision(self):
        found = autoplay.decisions([frame([ATTACK, BIG_ATTACK], points=True, weakness="Instinct"),
                                    frame([BIG_ATTACK], points=True, weakness="Instinct")])
        self.assertEqual(found[0].weakness, "Instinct")
        self.assertTrue(found[0].points)


class TestTurns(unittest.TestCase):
    """The turn-level view, which counts everything that left however fast Auto played it."""

    def test_a_turn_collects_every_departure(self):
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK, HEAL]), frame([BIG_ATTACK, HEAL]),
                                frame([HEAL])])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].played, Counter({ATTACK: 1, BIG_ATTACK: 1}))

    def test_a_turn_counts_cards_lost_faster_than_we_sampled(self):
        # Two leaving at once is useless as a label but still tells us Auto spent the turn on both.
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK, HEAL]), frame([HEAL])])
        self.assertEqual(found[0].played, Counter({ATTACK: 1, BIG_ATTACK: 1}))
        self.assertTrue(found[0].ambiguous)

    def test_a_clean_turn_is_not_ambiguous(self):
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK]), frame([BIG_ATTACK])])
        self.assertFalse(found[0].ambiguous)

    def test_the_deal_starts_a_new_turn(self):
        # The old hand is discarded before the new one arrives, which is what tells a deal apart from a card
        # that drew. Here BIG_ATTACK is played, the last card goes, and a fresh four are dealt.
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK]), frame([BIG_ATTACK]),
                                frame([HEAL, DRAWER, ATTACK, "Freezing Blade"]),
                                frame([HEAL, DRAWER, ATTACK])])
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].opening, (ATTACK, BIG_ATTACK))
        self.assertEqual(found[1].played, Counter({"Freezing Blade": 1}))

    def test_a_card_that_drew_is_not_a_new_turn(self):
        # Drawing grows the hand just as a deal does, but what was already held stays put.
        found = autoplay.turns([frame([DRAWER, ATTACK]), frame([ATTACK, HEAL, BIG_ATTACK])])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].played, Counter({DRAWER: 1}))

    def test_the_end_of_turn_discard_is_not_counted_as_played(self):
        # The whole hand vanishes as the next one is dealt. Counting that would say Auto played everything.
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK]), frame([HEAL, DRAWER, "Freezing Blade"])])
        self.assertEqual(found[0].played, Counter())

    def test_spent_points_coming_back_starts_a_turn_even_if_a_name_carried_over(self):
        # A deck with several copies of a card deals the same name into consecutive hands often enough that
        # "everything left" cannot be the only test. Points refreshing is what settles it.
        found = autoplay.turns([frame([ATTACK, BIG_ATTACK], points=False),
                                frame([HEAL, DRAWER, ATTACK], points=True)])
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].played, Counter())

    def test_an_empty_recording_reconstructs_nothing(self):
        self.assertEqual(autoplay.decisions([]), [])
        self.assertEqual(autoplay.turns([]), [])


if __name__ == "__main__":
    unittest.main()
