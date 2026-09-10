"""Check how a Desire card's faction tag is read off the screen.

Season 4 prints a tag on any card carrying Desire: `[ Inquiry ]` at level one, `[ Inquiry 2 ]` at level two,
and `[ Control / Inquiry 2 ]` once two factions have been merged into one card. Faction and points are both in
that one string, so nothing has to be tracked across a run - which matters, because a run can be resumed or
the bot restarted mid-node.

Every reading here is either from the captured screens or from a real Chaos run's log, including the mangled
ones. The reader loses brackets often and runs the tag into the effect text below it, so the shape test has to
turn those away rather than guess: acting on a misread tag would steer a whole run's card picks wrongly, while
skipping one costs a single frame out of a screen the bot sees once a second.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.desire import FACTIONS, MAX_LEVEL, points_of, tags_of  # noqa: E402


class TestTagsOf(unittest.TestCase):
    """Reading faction and points out of a tag."""

    def test_a_plain_tag_is_one_point(self):
        self.assertEqual({"Inquiry": 1}, tags_of("[ Inquiry ]"))

    def test_a_numbered_tag_carries_its_points(self):
        self.assertEqual({"Inquiry": 2}, tags_of("[ Inquiry 2 ]"))

    def test_a_merged_tag_carries_both(self):
        self.assertEqual({"Control": 1, "Inquiry": 2}, tags_of("[ Control / Inquiry 2 ]"))

    def test_the_order_of_a_merged_tag_does_not_matter(self):
        self.assertEqual(tags_of("[ Control / Inquiry 2 ]"), tags_of("[ Inquiry 2 / Control ]"))

    def test_every_faction_is_read(self):
        for faction in FACTIONS:
            with self.subTest(faction=faction):
                self.assertEqual({faction: 1}, tags_of(f"[ {faction} ]"))

    def test_a_lost_opening_bracket_still_reads(self):
        # The reader drops one bracket often; the log has "Control]" on its own line.
        self.assertEqual({"Control": 1}, tags_of("Control]"))

    def test_missing_spaces_still_read(self):
        self.assertEqual({"Claim": 2, "Survival": 1}, tags_of("[Claim 2 /Survival]"))

    def test_letter_case_does_not_matter(self):
        self.assertEqual({"Survival": 1}, tags_of("[survival]"))

    def test_effect_text_is_not_a_tag(self):
        for text in ("Draw 1", "3 Vulnerable to targets that possess harmful effects",
                     "1 Weaken and 3 Scorched to all enemies", "Skill", ""):
            with self.subTest(text=text):
                self.assertEqual({}, tags_of(text))

    def test_a_tag_run_into_the_effect_is_refused(self):
        # From a real run: the reader glued the tag to the sentence under it. Reading a faction out of this
        # would be right, but reading its points would not, so the whole thing is turned away.
        self.assertEqual({}, tags_of("Control200% Damage to allDefeat: 4Scorched to aenemiesrandom enemy"))

    def test_a_faction_word_in_a_sentence_is_refused(self):
        self.assertEqual({}, tags_of("Gain Control of a random enemy for 1 turn"))

    def test_points_beyond_the_level_cap_are_refused(self):
        # A card stops at level three, so a bigger number came from the effect text running into the tag -
        # "Control200% Damage" was a real reading.
        self.assertEqual({}, tags_of(f"[ Control {MAX_LEVEL + 1} ]"))
        self.assertEqual({}, tags_of("[ Control 200 ]"))

    def test_a_merged_tag_beyond_the_cap_is_refused(self):
        self.assertEqual({}, tags_of(f"[ Control {MAX_LEVEL} / Inquiry {MAX_LEVEL} ]"))

    def test_a_tag_exactly_at_the_cap_is_kept(self):
        self.assertEqual({"Control": MAX_LEVEL}, tags_of(f"[ Control {MAX_LEVEL} ]"))

    def test_a_garbled_faction_word_is_refused(self):
        # "tContirol / survival" is what one frame actually produced.
        self.assertEqual({}, tags_of("tContirol / survival"))


class TestPointsOf(unittest.TestCase):
    """Totalling a tag."""

    def test_totals_a_merged_tag(self):
        self.assertEqual(3, points_of(tags_of("[ Control / Inquiry 2 ]")))

    def test_a_level_one_card_is_one_point(self):
        self.assertEqual(1, points_of(tags_of("[ Inquiry ]")))

    def test_nothing_is_no_points(self):
        self.assertEqual(0, points_of({}))

    def test_the_total_is_the_cards_level(self):
        # Captured: Lv. 1 reads "[ Inquiry ]", Lv. 2 reads "[ Inquiry 2 ]", Lv. 3 reads "[ Control /
        # Inquiry 2 ]". The tag total is the level, which is what caps a card at three.
        for level, tag in ((1, "[ Inquiry ]"), (2, "[ Inquiry 2 ]"), (3, "[ Control / Inquiry 2 ]")):
            with self.subTest(level=level):
                self.assertEqual(level, points_of(tags_of(tag)))


if __name__ == "__main__":
    unittest.main()
