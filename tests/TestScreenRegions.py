"""Check the shared reading of a region off the screen.

`src/en/screen.py` exists so the centre-in-a-band arithmetic is written once. `text_in_region` is the other
half of that: nearly every fork-local handler wants "the box in this band whose text contains this", and
writing the loop out per module is how four near-identical copies appeared.

The pixel side is here for the same reason. `patch_of` and `colour_share` are what three modules now judge a
patch of frame by, and the case worth pinning is the one a caller cannot see going wrong: a box that runs off
the frame would otherwise come back as a strip of whatever sits at the edge, reading as a confident answer
about the wrong pixels.
"""

import sys
import unittest
from functools import partial
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.screen import colour_share, frame_of, in_region, patch_of, text_in_region  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
BAND = (0.400, 0.400, 0.600, 0.600)
# An amber the size of the band the auto-advance button is read on, as OpenCV BGR and HSV bounds.
AMBER = (77, 111, 156)
AMBER_LOW = np.array((10, 90, 120), dtype=np.uint8)
AMBER_HIGH = np.array((35, 255, 255), dtype=np.uint8)


# These helpers take boxes placed by share of the screen.
FakeBox = partial(Box, width=90, height=30, units="fraction")


class FakeTask:
    """A task holding one OCR pass and one capture."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes, frame=None):
        self.all_texts = boxes
        self.frame = frame


class TestTextInRegion(unittest.TestCase):
    """Finding a caption inside a band."""

    def test_finds_a_box_whose_text_contains_the_needle(self):
        box = FakeBox("Free", 0.5, 0.5)
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))

    def test_matches_on_a_substring(self):
        box = FakeBox("SOLD OUT Free refresh", 0.5, 0.5)
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))

    def test_ignores_letter_case(self):
        box = FakeBox("Combatants are limited to 1 piece of Mythic-grade equipment.", 0.5, 0.5)
        self.assertIsNotNone(text_in_region(FakeTask([box]), "mythic", BAND))

    def test_ignores_a_match_outside_the_band(self):
        self.assertIsNone(text_in_region(FakeTask([FakeBox("Free", 0.9, 0.9)]), "Free", BAND))

    def test_returns_none_when_nothing_matches(self):
        self.assertIsNone(text_in_region(FakeTask([FakeBox("Buy", 0.5, 0.5)]), "Free", BAND))

    def test_returns_the_first_match_in_reading_order(self):
        first, second = FakeBox("Free a", 0.45, 0.5), FakeBox("Free b", 0.55, 0.5)
        self.assertIs(first, text_in_region(FakeTask([first, second]), "Free", BAND))

    def test_survives_a_task_with_no_pass_yet(self):
        self.assertIsNone(text_in_region(FakeTask(None), "Free", BAND))

    def test_uses_the_same_containment_rule_as_in_region(self):
        # One rule, so a band that works for a caption works for anything else read off the screen.
        box = FakeBox("Free", 0.5, 0.5)
        self.assertTrue(in_region(box, BAND, WIDTH, HEIGHT))
        self.assertIs(box, text_in_region(FakeTask([box]), "Free", BAND))


class TestPatchOf(unittest.TestCase):
    """Cutting a relative box out of a frame."""

    def setUp(self):
        self.frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

    def test_cuts_the_box_the_caller_asked_for(self):
        patch = patch_of(self.frame, BAND)
        self.assertEqual((round(0.2 * HEIGHT), round(0.2 * WIDTH), 3), patch.shape)

    def test_no_frame_offers_nothing(self):
        self.assertIsNone(patch_of(None, BAND))

    def test_a_box_running_off_the_frame_offers_nothing(self):
        # Clamping would hand back a strip of the edge, which reads as a confident answer about the wrong
        # pixels rather than as the miss it is.
        for box in ((0.9, 0.4, 1.4, 0.6), (-0.1, 0.4, 0.2, 0.6), (0.4, 0.4, 0.2, 0.6)):
            with self.subTest(box=box):
                self.assertIsNone(patch_of(self.frame, box))

    def test_a_capture_with_an_alpha_channel_loses_it(self):
        # The client's captures are four channels on some paths, and every reading downstream converts from
        # BGR, which fails outright on a fourth.
        opaque = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
        self.assertEqual(3, patch_of(opaque, BAND).shape[2])

    def test_reads_the_frame_off_the_task(self):
        self.assertIs(self.frame, frame_of(FakeTask(None, self.frame)))

    def test_a_task_with_no_capture_yet_offers_nothing(self):
        self.assertIsNone(frame_of(FakeTask(None)))


class TestColourShare(unittest.TestCase):
    """Measuring how much of a patch is drawn in one band of colour."""

    def test_a_patch_drawn_entirely_in_the_colour_is_all_of_it(self):
        patch = np.full((40, 40, 3), AMBER, dtype=np.uint8)
        self.assertEqual(1.0, colour_share(patch, AMBER_LOW, AMBER_HIGH))

    def test_a_patch_drawn_in_nothing_like_it_is_none_of_it(self):
        patch = np.zeros((40, 40, 3), dtype=np.uint8)
        self.assertEqual(0.0, colour_share(patch, AMBER_LOW, AMBER_HIGH))

    def test_half_a_patch_reads_as_half(self):
        patch = np.zeros((40, 40, 3), dtype=np.uint8)
        patch[:20] = AMBER
        self.assertEqual(0.5, colour_share(patch, AMBER_LOW, AMBER_HIGH))

    def test_nothing_to_read_is_none_of_it_rather_than_a_crash(self):
        self.assertEqual(0.0, colour_share(None, AMBER_LOW, AMBER_HIGH))
        self.assertEqual(0.0, colour_share(np.zeros((0, 0, 3), dtype=np.uint8), AMBER_LOW, AMBER_HIGH))


if __name__ == "__main__":
    unittest.main()
