"""Check what the picker manages to read off a battle screen.

Two kinds of fixture sit behind this. The cut-outs are real pixels and pin the colour thresholds: the Action
Point readouts are deliberately the hardest pair the captures offer, the zero with the most background
bleeding into it and the lowest positive reading seen, so anything that closes that gap fails here first.
The painted frames pin the geometry, where what matters is the size and placement rather than the exact
colour - and `enemy_instinct` is there so the sizes are held to what the game draws and not to what the
painter draws.
"""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import board  # noqa: E402

IMAGES = REPO_ROOT / "tests" / "images"
WIDTH, HEIGHT = 1920, 1080

# Where each cut-out sat in the frame it came from. The readings are all in fractions of the frame, so a crop
# only means what it meant once it is back at the size and place it was cut from. `enemy_instinct` is one
# enemy of `battle_000`, counter and attribute badge together. `attack_flash` is the magenta burst thrown up
# by a hit landing in `battle_003`, which is square enough and large enough to pass everything but the height.
ENEMY_AT = (1238, 203)
FLASH_AT = (1000, 454)


def fixture(name):
    """Load one of the cut-outs.

    Args:
        name: The file's base name.

    Returns:
        The image as the framework hands frames over, in BGR.
    """
    return cv2.imread(str(IMAGES / f"{name}.png"))


class FakeTask:
    """A task holding one frame, which is all the board reading needs."""

    def __init__(self, frame):
        self.frame = frame
        self.height, self.width = frame.shape[:2]


def flat(value):
    """Build a frame of one brightness, for testing the reading rather than the game.

    Args:
        value: The grey level to fill it with.

    Returns:
        A full-size frame.
    """
    return np.full((HEIGHT, WIDTH, 3), value, dtype=np.uint8)


def pasted(name, left, top):
    """Put a cut-out back into a full frame at the place it came from.

    Args:
        name: The file's base name.
        left: Where its left edge sat.
        top: Where its top edge sat.

    Returns:
        A full-size frame, black apart from the cut-out.
    """
    patch = fixture(name)
    frame = flat(0)
    height, width = patch.shape[:2]
    frame[top:top + height, left:left + width] = patch
    return frame


class TestLitFraction(unittest.TestCase):
    """The measurement itself, on the readouts as they really appear."""

    def test_a_zero_is_mostly_dark(self):
        self.assertLess(board.lit_fraction(fixture("action_points_none")), board.LIT_ENOUGH)

    def test_a_positive_reading_is_mostly_lit(self):
        self.assertGreater(board.lit_fraction(fixture("action_points_some")), board.LIT_ENOUGH)

    def test_the_two_are_not_close(self):
        # The digit is drawn bright blue when there are points to spend and thin grey when there are none, so
        # the gap is a property of the game's own rendering rather than a threshold tuned onto noise.
        dark = board.lit_fraction(fixture("action_points_none"))
        lit = board.lit_fraction(fixture("action_points_some"))
        self.assertGreater(lit - dark, 0.05)


class TestActionPoints(unittest.TestCase):
    """The answer the planner actually asks for."""

    def test_an_unlit_readout_means_no_points_left(self):
        self.assertFalse(board.has_action_points(FakeTask(flat(0))))

    def test_a_lit_readout_means_points_remain(self):
        self.assertTrue(board.has_action_points(FakeTask(flat(255))))

    def test_a_frame_that_is_missing_is_not_an_answer(self):
        # `task.frame` is None while capture is between frames, and guessing "no points" there would end a
        # turn that had not finished.
        self.assertTrue(board.has_action_points(FakeTask.__new__(FakeTask)))


def paint(frame, slots):
    """Colour the Ego cost badges of the named slots the blue the game uses for an affordable one.

    Args:
        frame: The frame to draw on.
        slots: The slot keys to light up.

    Returns:
        The frame, for chaining.
    """
    height, width = frame.shape[:2]
    for slot in slots:
        left, top, right, bottom = board.box_around(board.EGO_BADGE_X, board.EGO_BADGE_Y[slot],
                                                    board.EGO_BADGE_HALF)
        frame[int(top * height):int(bottom * height), int(left * width):int(right * width)] = (230, 150, 60)
    return frame


class TestEgoBadges(unittest.TestCase):
    """Which Ego skills the EP bar can actually pay for, read off the badge beside each one."""

    def test_an_affordable_badge_reads_blue(self):
        self.assertGreater(board.blue_fraction(fixture("ego_badge_ready")), board.EGO_READY)

    def test_a_badge_that_cannot_be_paid_for_has_no_blue_at_all(self):
        self.assertEqual(board.blue_fraction(fixture("ego_badge_spent")), 0.0)

    def test_the_slots_that_are_lit_are_the_ones_offered(self):
        task = FakeTask(paint(flat(0), ("F1", "F3")))
        self.assertEqual(board.affordable_egos(task), ["F1", "F3"])

    def test_nothing_lit_offers_nothing(self):
        self.assertEqual(board.affordable_egos(FakeTask(flat(0))), [])

    def test_slots_come_back_in_the_order_they_are_shown(self):
        task = FakeTask(paint(flat(0), ("F3", "F2", "F1")))
        self.assertEqual(board.affordable_egos(task), ["F1", "F2", "F3"])

    def test_no_frame_offers_nothing(self):
        # Firing an Ego blind is what this replaces, so an unreadable frame has to decline rather than guess.
        self.assertEqual(board.affordable_egos(FakeTask.__new__(FakeTask)), [])


def in_hue(hue, saturation=220, value=220):
    """Build a BGR colour at one hue, the way the game draws its badges.

    Args:
        hue: The OpenCV hue, 0 to 179.
        saturation: How saturated to make it.
        value: How bright to make it.

    Returns:
        The colour as a BGR tuple.
    """
    pixel = np.array([[[hue, saturation, value]]], dtype=np.uint8)
    return tuple(int(channel) for channel in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0][0])


def paint_enemy(frame, centre_x, centre_y, hue):
    """Draw an enemy's action counter and the attribute badge beside it.

    Args:
        frame: The frame to draw on.
        centre_x: Where the counter sits across the frame.
        centre_y: Where the counter sits down the frame.
        hue: The hue to draw the attribute badge in.

    Returns:
        The frame, for chaining.
    """
    height, width = frame.shape[:2]
    # Sized as the game draws it, since how tall a counter is now decides whether it is one.
    half = int(0.057 * height / 2)
    counter_x, counter_y = int(centre_x * width), int(centre_y * height)
    frame[counter_y - half:counter_y + half, counter_x - half:counter_x + half] = in_hue(170, 230, 200)
    left, top, right, bottom = board.box_around(centre_x + board.WEAKNESS_OFFSET[0],
                                                centre_y + board.WEAKNESS_OFFSET[1], board.WEAKNESS_HALF)
    frame[int(top * height):int(bottom * height), int(left * width):int(right * width)] = in_hue(hue)
    return frame


class TestWeaknessBadges(unittest.TestCase):
    """The attribute an enemy is weak to, read off the badge beside its action counter."""

    def test_the_instinct_badge_is_recognised(self):
        # The one reading confirmed against the game itself.
        self.assertEqual(board.attribute_of(fixture("weakness_instinct")), "Instinct")

    def test_the_other_two_colours_seen_so_far(self):
        self.assertEqual(board.attribute_of(fixture("weakness_order")), "Order")
        self.assertEqual(board.attribute_of(fixture("weakness_void")), "Void")

    def test_a_patch_with_no_badge_in_it_says_nothing(self):
        self.assertIsNone(board.attribute_of(np.full((18, 33, 3), 60, dtype=np.uint8)))

    def test_the_counters_own_magenta_is_not_an_attribute(self):
        # Magenta sits next to red on the hue wheel, so a patch that catches the counter itself - or any of
        # the effects the game draws in that colour - would otherwise read as a confident Passion.
        magenta = np.full((18, 33, 3), in_hue(170, 230, 200), dtype=np.uint8)
        self.assertIsNone(board.attribute_of(magenta))

    def test_a_fight_where_every_enemy_shares_a_weakness(self):
        frame = flat(0)
        paint_enemy(frame, 0.50, 0.25, board.ATTRIBUTE_HUES["ORANGE"])
        paint_enemy(frame, 0.70, 0.30, board.ATTRIBUTE_HUES["ORANGE"])
        self.assertEqual(board.weakness(FakeTask(frame)), "Instinct")

    def test_enemies_that_disagree_give_no_preference(self):
        # The attribute is only ever a tie-break, so a majority would be defensible, but no capture so far
        # shows a mixed fight to check one against. Having no opinion is the answer that cannot be wrong.
        frame = flat(0)
        paint_enemy(frame, 0.50, 0.25, board.ATTRIBUTE_HUES["ORANGE"])
        paint_enemy(frame, 0.70, 0.30, board.ATTRIBUTE_HUES["GREEN"])
        self.assertIsNone(board.weakness(FakeTask(frame)))

    def test_a_magenta_flash_is_not_an_enemy(self):
        # An attack landing throws up a magenta burst the same colour as a counter but many times its size.
        frame = flat(0)
        paint_enemy(frame, 0.50, 0.25, board.ATTRIBUTE_HUES["ORANGE"])
        frame[int(0.30 * HEIGHT):int(0.50 * HEIGHT), int(0.60 * WIDTH):int(0.90 * WIDTH)] = in_hue(170, 230, 200)
        self.assertEqual(len(board.enemy_counters(frame)), 1)

    def test_an_enemy_at_the_frame_edge_is_not_guessed_at(self):
        # Its badge would sit off screen, and sampling what little is left reads as a confident answer about
        # the scenery rather than about an enemy.
        frame = paint_enemy(flat(0), 0.985, 0.30, board.ATTRIBUTE_HUES["ORANGE"])
        self.assertIsNone(board.weakness(FakeTask(frame)))

    def test_no_enemies_found_means_no_preference(self):
        self.assertIsNone(board.weakness(FakeTask(flat(0))))

    def test_no_frame_means_no_preference(self):
        self.assertIsNone(board.weakness(FakeTask.__new__(FakeTask)))


class TestRealEnemies(unittest.TestCase):
    """The same reading against the game's own rendering, which is what the sizes were measured from.

    The painted frames above would still pass if the counter size, the badge offset and the badge size all
    drifted together. These would not, so this is where those four constants are actually held.
    """

    def test_a_real_counter_is_found(self):
        self.assertEqual(len(board.enemy_counters(pasted("enemy_instinct", *ENEMY_AT))), 1)

    def test_a_real_enemy_reads_its_weakness(self):
        self.assertEqual(board.weakness(FakeTask(pasted("enemy_instinct", *ENEMY_AT))), "Instinct")

    def test_a_real_attack_flash_is_not_an_enemy(self):
        # It is the right colour, well over the minimum area and within the squareness band, so the height is
        # the only thing keeping a hit landing from being counted as another enemy.
        self.assertEqual(board.enemy_counters(pasted("attack_flash", *FLASH_AT)), [])


if __name__ == "__main__":
    unittest.main()
