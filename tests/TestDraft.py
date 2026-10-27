"""Check which combatant the bot drafts for the team it has, and when it spends a reroll.

A reroll cannot be taken back, and a badge matched to the wrong card would rank every candidate wrongly, so
both the badge-to-card pairing and the spend condition are pinned here. Positions are the draft screen's.
"""

import sys
import unittest
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.draft import ROLES, badges, choose, rank, rerollable, role_for, role_of, wanted  # noqa: E402
from src.en.game_quality import COMBATANT_ROLE  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
# Where the three cards sit, measured off the screen the run captured.
CARDS = (("Rin", 0.322), ("Beryl", 0.586), ("Magna", 0.851))
BADGE_Y, NAME_Y, REROLL_Y = 0.675, 0.724, 0.807


# The draft screen places its boxes by share of the screen.
FakeBox = partial(Box, width=80, height=26, units="fraction")


class FakeTask:
    """A task holding one OCR pass of the draft screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes


def draft_screen(roles=("Core", "攻击力", "Protection"), counters=("1/1", "1/1", "1/1")):
    """Build the draft screen as the reader sees it.

    Args:
        roles: The badge text on each card, left to right.
        counters: The reroll counter on each card, left to right.

    Returns:
        A `FakeTask`.
    """
    boxes = []
    for (name, x), role, counter in zip(CARDS, roles, counters):
        boxes.append(FakeBox(role, x, BADGE_Y))
        boxes.append(FakeBox(name, x, NAME_Y))
        boxes.append(FakeBox(counter, x + 0.013, REROLL_Y))
    return FakeTask(boxes)


def slot(name, x):
    """Build the slot dict `_read_member_slots` produces.

    Args:
        name: The candidate's name.
        x: The name box's centre.

    Returns:
        The slot dict.
    """
    return {"name": name, "x": x, "y": NAME_Y, "refresh_y": REROLL_Y}


class TestDraft(unittest.TestCase):

    def test_the_badge_readings_are_recognised(self):
        self.assertEqual("Core", role_of("Core"))
        self.assertEqual("Protection", role_of("Protection"))

    def test_the_rewritten_attack_badge_is_recognised(self):
        """The catalog rewrites Attack to 攻击力 for the card type label, and the badge shares the word."""
        self.assertEqual("Attack", role_of("攻击力"))
        self.assertEqual("Attack", role_of("Attack"))

    def test_text_that_is_not_a_badge_is_ignored(self):
        for text in ("Rin", "1/1", "LV", "", None):
            with self.subTest(text=text):
                self.assertIsNone(role_of(text))

    def test_each_badge_belongs_to_its_own_card(self):
        """Pairing a badge with the wrong card would rank all three wrongly."""
        task = draft_screen()
        found = badges(task)
        paired = {name: role_for(slot(name, x), found) for name, x in CARDS}
        self.assertEqual({"Rin": "Core", "Beryl": "Attack", "Magna": "Protection"}, paired)

    def test_an_unread_badge_ranks_last(self):
        """A card whose badge did not read must never outrank one that did."""
        self.assertGreater(rank(None), rank("Protection"))

    def test_the_best_of_the_real_draft_is_the_core(self):
        task = draft_screen()
        found = badges(task)
        best = min(CARDS, key=lambda card: rank(role_for(slot(*card), found)))
        self.assertEqual("Rin", best[0])

    def test_the_team_drafts_the_role_it_lacks(self):
        """A second damage dealer is only a fallback once the rerolls are spent."""
        cases = [
            # (team, offers, can reroll, expected pick or None for a reroll)
            ({"Hugo"}, ("Beryl", "Hilde", "Khalipe"), True, "Khalipe"),
            ({"Hugo"}, ("Khalipe", "Mika", "Cassius"), True, "Mika"),
            ({"Hugo", "Mika"}, ("Cassius", "Khalipe", "Rin"), True, "Khalipe"),
            ({"Hugo"}, ("Beryl", "Rin", "Hilde"), True, None),
            ({"Hugo"}, ("Beryl", "Rin", "Hilde"), False, "Rin"),
            ({"Mika"}, ("Khalipe", "Beryl", "Cassius"), True, "Beryl"),
            (set(), ("Khalipe", "Beryl", "Rin"), True, "Rin"),
        ]
        for party, offers, can_reroll, expected in cases:
            with self.subTest(party=party, offers=offers, can_reroll=can_reroll):
                pick = choose([COMBATANT_ROLE[name] for name in offers], wanted(party), can_reroll)
                self.assertEqual(expected, None if pick is None else offers[pick])

    def test_every_role_in_the_data_is_one_the_draft_ranks(self):
        """A patch renaming a role would rank that whole role below an unread badge."""
        self.assertLessEqual(set(COMBATANT_ROLE.values()), set(ROLES))

    def test_an_unspent_slot_can_be_rerolled(self):
        task = draft_screen()
        self.assertTrue(all(rerollable(task, slot(name, x)) for name, x in CARDS))

    def test_a_spent_slot_is_never_rerolled_again(self):
        """The counter reads 0/1 once used, and clicking it again would waste a frame every pass."""
        task = draft_screen(counters=("0/1", "1/1", "0/1"))
        spent = [name for name, x in CARDS if not rerollable(task, slot(name, x))]
        self.assertEqual(["Rin", "Magna"], spent)

    def test_a_slot_with_no_reroll_button_is_never_rerolled(self):
        task = draft_screen()
        no_button = {"name": "Rin", "x": 0.322, "y": NAME_Y, "refresh_y": None}
        self.assertFalse(rerollable(task, no_button))


if __name__ == "__main__":
    unittest.main()
