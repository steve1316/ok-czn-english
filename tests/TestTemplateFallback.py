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
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from ok import Box  # noqa: E402
from ok.feature.FeatureSet import FeatureSet  # noqa: E402

import utils  # noqa: E402

from src.en import templates  # noqa: E402
from src.en.handlers import standing_in  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

# The free Epiphany icon over a combatant at camp, cropped from Global client frames: the largest size from the 2026-10-25
# run, the middle from a 2026-10-28 camp the run walked past, the smallest from a 2026-10-29 camp walked past on restart.
CAMP_EPIPHANIES = [REPO_ROOT / "tests" / "images" / name
                   for name in ("camp_epiphany.png", "camp_epiphany_small.png", "camp_epiphany_smallest.png")]
# The templates `handle_rest` tries for that icon, both at once.
CAMP_TEMPLATES = ["special_flash_luosi", "special_flash_luosi2"]
# The region `handle_rest` searches for that icon, in pixels of a 1920x1080 frame.
CAMP_REGION = Box(420, 225, 1089, 654)
# Upstream's `default_threshold` in `src/config.py`, which `handle_rest` matches the icon against.
THRESHOLD = 0.8
# The icon matches upstream found on the 2026-10-27 Obtain Card screen, as (centre x, centre y, confidence) per template.
# Each Upgrade match is the sparkle beside a party card's portrait, just above the Skill icon on that card.
REWARD_ICONS = {
    "attack": [(0.1844, 0.3472, 0.917)],
    "skill": [(0.461, 0.348, 0.790), (0.738, 0.347, 0.728)],
    "enhance": [(0.388, 0.309, 0.794), (0.665, 0.309, 0.785)],
}
# What OCR read off that screen, one name, type and description per card.
REWARD_TEXTS = [
    ("Harmonization: Moon of Destruction", 0.2458, 0.3125), ("攻击", 0.22, 0.345), ("528% Damage", 0.229, 0.65),
    ("Distortion: Financial Therapy", 0.5208, 0.313), ("技能", 0.4849, 0.3454), ("Heal 264%", 0.505, 0.679),
    ("Dark Condensation", 0.798, 0.313), ("技能", 0.7552, 0.3454), ("Select 1 Attack Card(s)", 0.78, 0.648),
]


class FakeTask:
    """Stands in for a running task holding the current OCR pass."""

    def __init__(self, all_texts):
        self.all_texts = all_texts


def scored(box, confidence):
    """Give a box the confidence upstream's recognizer logs and ranks by.

    Args:
        box: The `FakeBox` to score.
        confidence: The OCR or template-match confidence, from 0 to 1.

    Returns:
        The same box.
    """
    box.confidence = confidence
    return box


class RewardScreen:
    """Stands in for a task looking at the Obtain Card screen, for upstream's own card recognizer."""

    width, height = 1920, 1080

    def __init__(self):
        self.all_texts = [scored(FakeBox(name, x, y, units="fraction"), 1.0) for name, x, y in REWARD_TEXTS]

    def find_feature(self, feature_name=None, box=None, threshold=0):
        return [scored(FakeBox(feature_name, x, y, width=30, height=30, units="fraction"), confidence)
                for x, y, confidence in REWARD_ICONS.get(feature_name, ())]

    def box_of_screen(self, *region):
        return region

    def log_info(self, message):
        pass


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

    def test_every_size_of_the_camp_epiphany_icon_is_found(self):
        """Resizing a template in place lost the size it matched as is, so the free Epiphany at camp was walked past."""
        feature_set = FeatureSet(False, str(REPO_ROOT / "ok_tasks" / "assets" / "coco_annotations.json"), 0.002, 0.002, THRESHOLD)
        for path in CAMP_EPIPHANIES:
            with self.subTest(icon=path.name):
                frame = np.zeros((1080, 1920, 3), np.uint8)
                frame[310:470, 640:800] = cv2.imread(str(path))
                find = lambda name, **kwargs: feature_set.find_feature(frame, name, **kwargs)
                get_feature = lambda name: feature_set.get_feature_by_name(frame, name)
                self.assertTrue(templates.find_at_any_size(find, get_feature, CAMP_TEMPLATES, box=CAMP_REGION))

    def test_a_sparkle_beside_a_portrait_does_not_hide_the_card(self):
        """The sparkle out-scored the Skill icon on both party cards, so the reward was skipped as offering nothing wanted."""
        screen = RewardScreen()
        self.assertEqual(["Harmonization: Moon of Destruction"], [card["name"] for card in utils.recognize_cards(screen)])
        named = templates.named_only(utils._recognize_cards_by_features, utils)
        with standing_in(utils, _recognize_cards_by_features=named):
            cards = utils.recognize_cards(screen)
        self.assertEqual(["Harmonization: Moon of Destruction", "Distortion: Financial Therapy", "Dark Condensation"],
                         [card["name"] for card in cards])

    def test_the_patch_is_idempotent(self):
        from ok.task.task import FindFeature

        templates.apply()
        once = FindFeature.find_feature
        templates.apply()
        self.assertIs(once, FindFeature.find_feature)


if __name__ == "__main__":
    unittest.main()
