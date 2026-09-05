"""Check the stand-in for the one template that is a picture of a Chinese word.

`src/en/templates.py` only steps in when the real template matched nothing, so the risk is at the edges: a
Chinese client losing its template matches, or the fallback answering for a feature it has no business
answering for. Both are asserted here, along with the region filter - `_find_member_level_tags` reads the
returned boxes' coordinates, so a box from the wrong part of the screen would bind equipment to the wrong
combatant.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ok import Box  # noqa: E402

from src.en import templates  # noqa: E402


class FakeTask:
    """Stands in for a running task holding the current OCR pass."""

    def __init__(self, all_texts):
        self.all_texts = all_texts


def caption(name, x, y):
    """Build an OCR box the size the client draws a LEVEL caption.

    Args:
        name: The box text.
        x: Left edge in pixels.
        y: Top edge in pixels.

    Returns:
        A `Box`.
    """
    return Box(x, y, 44, 17, name=name)


class TestTemplateFallback(unittest.TestCase):

    def setUp(self):
        # Three combatant rows down the right of the equipment screen, as the run captured them.
        self.task = FakeTask([
            caption("LEVEL", 1187, 339),
            caption("LEVEL", 1187, 579),
            caption("LEVEL", 1187, 819),
            caption("Reinforced Combat Suit", 360, 430),
            caption("Defense", 370, 495),
        ])

    def test_every_level_caption_is_found(self):
        self.assertEqual(3, len(templates.boxes_in(self.task, None, ("LEVEL",))))

    def test_a_region_excludes_captions_outside_it(self):
        """The caller restricts the search, and the boxes it gets back decide which combatant is picked."""
        region = Box(1100, 300, 400, 200)
        found = templates.boxes_in(self.task, region, ("LEVEL",))
        self.assertEqual([339], [box.y for box in found])

    def test_other_text_is_never_returned(self):
        self.assertEqual([], templates.boxes_in(self.task, None, ("VORTEX",)))

    def test_either_caption_is_accepted(self):
        """The catalog rewrites LV to 等级 for the draft screen, and could do the same to LEVEL."""
        chinese = FakeTask([caption("等级", 1187, 339), caption("等级", 1187, 579)])
        self.assertEqual(2, len(templates.resolve([], "leveltag", chinese, None)))
        self.assertEqual(3, len(templates.resolve([], "leveltag", self.task, None)))

    def test_the_caption_matches_regardless_of_case(self):
        self.assertEqual(3, len(templates.boxes_in(FakeTask([
            caption("Level", 1187, 339), caption("level", 1187, 579), caption(" LEVEL ", 1187, 819),
        ]), None, ("LEVEL",))))

    def test_only_leveltag_is_stood_in_for(self):
        """xuanwo_in_deck is the other Chinese-text template, but no code references it, so it is left alone."""
        self.assertEqual({"leveltag"}, set(templates.TEXT_TEMPLATES))

    def test_a_matching_template_is_never_overridden(self):
        """A Chinese client still matches the real template, and that result has to win untouched."""
        real = [caption("等级", 1187, 339)]
        self.assertIs(real, templates.resolve(real, "leveltag", self.task, None))

    def test_a_miss_falls_back_to_the_english_caption(self):
        self.assertEqual(3, len(templates.resolve([], "leveltag", self.task, None)))

    def test_other_features_are_left_alone_on_a_miss(self):
        """Every other template is an icon that matches both clients, so a miss there is a real miss."""
        self.assertEqual([], templates.resolve([], "flashmemberconfirm", self.task, None))
        self.assertEqual([], templates.resolve([], "hex_in_deck", self.task, None))

    def test_a_list_of_feature_names_is_passed_straight_through(self):
        """find_one searches several templates at once by passing a list, which is not hashable."""
        self.assertEqual([], templates.resolve([], ["memberinfo", "memberinfo2"], self.task, None))
        self.assertEqual([], templates.resolve([], None, self.task, None))

    def test_the_patch_is_idempotent(self):
        from ok.task.task import FindFeature

        templates.apply()
        once = FindFeature.find_feature
        templates.apply()
        self.assertIs(once, FindFeature.find_feature)


if __name__ == "__main__":
    unittest.main()
