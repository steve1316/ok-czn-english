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

    def test_a_tag_is_read_however_the_client_drew_it(self):
        """Each reading is a shape the client or the reader actually produces."""
        for description, text, expected in (
            ("a plain tag is one point", "[ Inquiry ]", {"Inquiry": 1}),
            ("a numbered tag carries its points", "[ Inquiry 2 ]", {"Inquiry": 2}),
            ("a merged tag carries both", "[ Control / Inquiry 2 ]", {"Control": 1, "Inquiry": 2}),
            # The reader drops one bracket often; the log has "Control]" on its own line.
            ("a lost opening bracket still reads", "Control]", {"Control": 1}),
            ("missing spaces still read", "[Claim 2 /Survival]", {"Claim": 2, "Survival": 1}),
            ("letter case does not matter", "[survival]", {"Survival": 1}),
        ):
            with self.subTest(description):
                self.assertEqual(expected, tags_of(text))

    def test_the_order_of_a_merged_tag_does_not_matter(self):
        self.assertEqual(tags_of("[ Control / Inquiry 2 ]"), tags_of("[ Inquiry 2 / Control ]"))

    def test_every_faction_is_read(self):
        for faction in FACTIONS:
            with self.subTest(faction=faction):
                self.assertEqual({faction: 1}, tags_of(f"[ {faction} ]"))

    def test_what_is_not_a_tag_is_refused(self):
        """A reading that is not a tag has to come back empty rather than half-read."""
        for description, text in (
            ("plain effect text", "Draw 1"),
            ("effect text with numbers", "3 Vulnerable to targets that possess harmful effects"),
            ("effect text naming two counts", "1 Weaken and 3 Scorched to all enemies"),
            ("a type label", "Skill"),
            ("nothing at all", ""),
            # From a real run: the reader glued the tag to the sentence under it. Reading a faction out of
            # this would be right, but reading its points would not, so the whole thing is turned away.
            ("a tag run into the effect", "Control200% Damage to allDefeat: 4Scorched to aenemiesrandom enemy"),
            ("a faction word in a sentence", "Gain Control of a random enemy for 1 turn"),
            # "tContirol / survival" is what one frame actually produced.
            ("a garbled faction word", "tContirol / survival"),
        ):
            with self.subTest(description):
                self.assertEqual({}, tags_of(text))

    def test_points_beyond_the_level_cap_are_refused(self):
        # A card stops at level three, so a bigger number came from the effect text running into the tag -
        # "Control200% Damage" was a real reading.
        self.assertEqual({}, tags_of(f"[ Control {MAX_LEVEL + 1} ]"))
        self.assertEqual({}, tags_of("[ Control 200 ]"))

    def test_a_merged_tag_beyond_the_cap_is_refused(self):
        self.assertEqual({}, tags_of(f"[ Control {MAX_LEVEL} / Inquiry {MAX_LEVEL} ]"))

    def test_a_tag_exactly_at_the_cap_is_kept(self):
        self.assertEqual({"Control": MAX_LEVEL}, tags_of(f"[ Control {MAX_LEVEL} ]"))


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
