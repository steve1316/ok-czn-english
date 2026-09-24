"""Check which screens the bot taps to advance, and which it leaves alone.

Two failure modes are worth pinning: missing a narration screen leaves the run stalled until someone stops it,
and matching something else means a stray click on a screen the bot has not learned yet. The event option
screen is the one that must never match - its text sits in the same band, centred the same, and only its width
tells the two apart.
"""

import sys
import time
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.dialogue import (AFTER_TAP, AFTER_TOGGLE, BUBBLE_AFTER_STUCK, MAX_TEXT_BOXES, MIN_GLOW,  # noqa: E402
                            TOGGLE_POINT, TOGGLE_REGION, TOGGLE_RETRY, TOGGLED_AT, auto_advance_off, handle_dialogue,
                            narration_line, speech_line)
from src.en.stuck import CLOCK  # noqa: E402

WIDTH, HEIGHT = 1920, 1080

# What the button is drawn in, sampled off the captured frames as OpenCV BGR. The lit ring's amber, and the
# neutral white of the padlock it shows while it is off.
GLOW = (77, 111, 156)
UNLIT = (168, 168, 168)
# The share of the patch the ring covers when it is lit. Twenty frames of the Global client were sampled over
# its patch: every frame showing it running ran 0.105 to 0.150 and every frame showing it off came back 0.000,
# so the thinnest of the lit ones is what the threshold has to sit under.
MEASURED_GLOW = 0.105

# The line the run stalled on, and the two-line screen the mushroom event showed.
SOLDIER = "The Soldier's eyes are fixed on the group. The Weapon in their hand is trembling."
MUSHROOM_FIRST = "The group examines the surface of the mushroom."
MUSHROOM_SECOND = "Blue, red, yellow, green. The spores come in a variety of colors."
# The speech bubble a Chaos run sat on for 38 seconds, drawn over the scene to the right of the party.
BUBBLE_FIRST = "The important thing is that just scraping this"
BUBBLE_SECOND = "together will make us rich!"


class FakeBox:
    """An OCR box positioned by its centre and its share of the screen width."""

    def __init__(self, name, center_x, center_y, width):
        self.name = name
        self.width = width * WIDTH
        self.height = 40
        self.x = center_x * WIDTH - self.width / 2
        self.y = center_y * HEIGHT - self.height / 2


class FakeTask:
    """A task holding one OCR pass and one capture, recording what the handler clicked."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes, frame=None):
        self.all_texts = boxes
        self.frame = frame
        self.clicked = None
        self.tapped = None
        self.moved = None
        self.slept = 0

    def click_box(self, box):
        self.clicked = box

    def click(self, x, y, after_sleep=0):
        self.tapped = (x, y)
        self.slept += after_sleep

    def move_relative(self, x, y):
        self.moved = (x, y)

    def sleep(self, seconds):
        self.slept += seconds

    def log_info(self, message):
        pass


def frame_with_button(color, share=1.0):
    """Build a capture whose auto-advance button is drawn in one colour.

    Args:
        color: The BGR the button is painted in.
        share: How much of the button's patch that colour covers, the rest left black.

    Returns:
        A `(height, width, 3)` BGR array.
    """
    left, top, right, bottom = TOGGLE_REGION
    x, y = int(left * WIDTH), int(top * HEIGHT)
    width, height = int(right * WIDTH) - x, int(bottom * HEIGHT) - y
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    frame[y:y + max(1, round(height * share)), x:x + width] = color
    return frame


def narration_screen():
    """Build the frame the run stalled on: health, credits and one line of prose.

    Returns:
        A `FakeTask`.
    """
    return FakeTask([
        FakeBox("2489/2658", 0.21, 0.038, 0.10),
        FakeBox("287", 0.65, 0.053, 0.02),
        FakeBox(SOLDIER, 0.496, 0.838, 0.716),
    ])


def two_line_narration_screen():
    """Build the mushroom event's dialogue screen, which reads out over two lines.

    Returns:
        A `FakeTask`.
    """
    return FakeTask([
        FakeBox("2542/2583", 0.21, 0.038, 0.10),
        FakeBox(MUSHROOM_FIRST, 0.467, 0.836, 0.508),
        FakeBox(MUSHROOM_SECOND, 0.512, 0.880, 0.591),
    ])


def option_screen():
    """Build the mushroom event's option screen, which must never be tapped.

    Its three option cards put text in the same band as narration, and the middle one is centred in the same
    place. Ranking the options is `src/en/events.py`'s job and a tap here would take that decision away.

    Returns:
        A `FakeTask`.
    """
    return FakeTask([
        FakeBox("2542/2583", 0.21, 0.038, 0.10),
        FakeBox("A single Invader mushroom has taken root here.", 0.5, 0.211, 0.35),
        FakeBox("It seems to contain a variety of spores.", 0.5, 0.248, 0.28),
        FakeBox("Examine the mushroom", 0.24, 0.799, 0.15),
        FakeBox("Check information on Types of", 0.24, 0.837, 0.22),
        FakeBox("[Dexterous] Collect a piece", 0.479, 0.799, 0.17),
        FakeBox("Upon success Decrease all", 0.479, 0.900, 0.21),
        FakeBox("Provoke the mushroom", 0.76, 0.799, 0.15),
        FakeBox("Event Encounter: [Pheromone", 0.76, 0.837, 0.21),
    ])


class TestDialogue(unittest.TestCase):

    def test_the_stalled_narration_screen_is_recognised(self):
        """The whole point: this frame held the run until it was stopped by hand."""
        line = narration_line(narration_screen())
        self.assertIsNotNone(line)
        self.assertEqual(SOLDIER, line.name)

    def test_a_two_line_narration_screen_is_recognised(self):
        self.assertIsNotNone(narration_line(two_line_narration_screen()))

    def test_the_option_screen_is_never_tapped(self):
        """Tapping here would take the choice away from the ranking, which is the decision that matters."""
        self.assertIsNone(narration_line(option_screen()))

    def test_a_line_that_is_not_prose_is_never_tapped(self):
        """Each row is a real screen out of the capture corpus that an earlier, looser rule wrongly matched."""
        for description, text, centre_x, centre_y, width in (
            # An option card's text is centred in the same band; only its width tells them apart.
            ("a narrow line", "Collect a piece", 0.5, 0.84, 0.17),
            # The event prompt is wide and centred too, but it sits at the top and is not a tap target.
            ("a line high on the screen", "A single Invader mushroom has taken root here.", 0.5, 0.211, 0.5),
            ("an off centre line", "something wide but off to one side", 0.78, 0.84, 0.5),
            # OCR hands back empty boxes, and one wide enough would otherwise be tapped as prose.
            ("a blank reading", "   ", 0.5, 0.84, 0.6),
        ):
            with self.subTest(description):
                task = FakeTask([FakeBox(text, centre_x, centre_y, width)])
                self.assertIsNone(narration_line(task))

    def test_an_empty_screen_is_not_narration(self):
        self.assertIsNone(narration_line(FakeTask([])))

    def test_a_busy_screen_is_not_narration(self):
        """A tip banner sits at narration height on a screen carrying dozens of readings. Narration dims the
        frame and takes the HUD with it, so the box count is what tells those apart."""
        boxes = [FakeBox(f"reading {index}", 0.2, 0.3, 0.05) for index in range(MAX_TEXT_BOXES)]
        boxes.append(FakeBox("When a Claim Card is used, gain 1 Claim: Desire for each stack.", 0.49, 0.872, 0.586))
        task = FakeTask(boxes)
        # Frozen too, so a bubble line cannot slip past the count either.
        setattr(task, CLOCK, time.time() - BUBBLE_AFTER_STUCK - 1)
        self.assertFalse(handle_dialogue(task))

    def test_a_line_on_the_button_row_is_not_narration(self):
        """Most of what the capture corpus wrongly matched sat at 0.908 and below, under the prose band."""
        task = FakeTask([FakeBox("You can receive Edit Data recommendations based on Build Preset info.",
                                 0.502, 0.936, 0.548)])
        self.assertIsNone(narration_line(task))

    def test_a_cutscene_line_is_narration(self):
        """The trauma centre's prose, captured in sortie_340: same shape, on a screen of its own."""
        task = FakeTask([
            FakeBox("Patient Name Mika Protocol 0, Hormones normalized.", 0.493, 0.834, 0.479),
            FakeBox("Parameters normalized.", 0.37, 0.878, 0.21),
        ])
        self.assertIsNotNone(narration_line(task))

    def test_the_handler_taps_the_line_and_claims_the_frame(self):
        task = narration_screen()
        self.assertTrue(handle_dialogue(task))
        self.assertIsNotNone(task.clicked)
        self.assertEqual(SOLDIER, task.clicked.name)

    def test_the_handler_waits_for_the_next_line_to_be_drawn(self):
        """Without the pause the same screen is read again before the tap has landed."""
        task = narration_screen()
        handle_dialogue(task)
        self.assertEqual(AFTER_TAP, task.slept)

    def test_the_handler_declines_a_screen_it_does_not_recognise(self):
        """Returning False is what lets the run loop carry on to whatever else might handle the frame."""
        task = option_screen()
        self.assertFalse(handle_dialogue(task))
        self.assertIsNone(task.clicked)


def bubble_screen(frozen_for):
    """Build the speech bubble frame the run stalled on, with the HUD still drawn around it.

    Args:
        frozen_for: How many seconds ago upstream's stuck clock last saw the picture change.

    Returns:
        A `FakeTask` holding the frame's OCR pass.
    """
    task = FakeTask([
        FakeBox("2229/2229", 0.21, 0.038, 0.10),
        FakeBox("153", 0.65, 0.053, 0.02),
        FakeBox(BUBBLE_FIRST, 0.688, 0.356, 0.308),
        FakeBox(BUBBLE_SECOND, 0.625, 0.394, 0.184),
    ])
    setattr(task, CLOCK, time.time() - frozen_for)
    return task


class TestSpeechBubble(unittest.TestCase):
    """An NPC's speech bubble, which sits over the scene rather than in the narration band."""

    def test_the_stalled_bubble_is_tapped_once_the_frame_has_frozen(self):
        task = bubble_screen(BUBBLE_AFTER_STUCK + 1)
        self.assertTrue(handle_dialogue(task))
        self.assertEqual(BUBBLE_FIRST, task.clicked.name)

    def test_a_bubble_is_left_alone_while_the_frame_is_still_changing(self):
        """The freeze is what says no other handler wants the frame, so a live frame is never read this loosely."""
        self.assertIsNone(speech_line(bubble_screen(0)))
        self.assertIsNone(speech_line(FakeTask(bubble_screen(0).all_texts)))

    def test_a_frozen_line_that_is_not_speech_is_never_tapped(self):
        for label, name, center_x, center_y, width in (
            ("a short label", "Event Encounter", 0.5, 0.4, 0.12),
            ("a line below the scene", "Select a card to remove", 0.5, 0.75, 0.2),
        ):
            with self.subTest(label):
                task = FakeTask([FakeBox(name, center_x, center_y, width)])
                setattr(task, CLOCK, time.time() - BUBBLE_AFTER_STUCK - 1)
                self.assertIsNone(speech_line(task))


class TestAutoAdvance(unittest.TestCase):
    """Reading the auto-advance button, and reaching for it before tapping the prose."""

    def test_the_lit_button_reads_as_running(self):
        """The thinnest ring the captures measured still has to clear the threshold."""
        task = FakeTask([], frame_with_button(GLOW, MEASURED_GLOW))
        self.assertFalse(auto_advance_off(task))

    def test_the_unlit_button_reads_as_off(self):
        """Off is drawn in a neutral white that carries no amber at all."""
        self.assertTrue(auto_advance_off(FakeTask([], frame_with_button(UNLIT))))

    def test_a_ring_thinner_than_the_threshold_reads_as_off(self):
        task = FakeTask([], frame_with_button(GLOW, MIN_GLOW / 2))
        self.assertTrue(auto_advance_off(task))

    def test_a_frame_the_reader_never_got_is_left_alone(self):
        """No capture means no reading, and a reading that fails must not put a click somewhere unasked."""
        self.assertFalse(auto_advance_off(FakeTask([])))

    def test_the_handler_turns_auto_advance_on_instead_of_tapping(self):
        """One tap on the button and the game plays the rest of the cutscene without the bot in the loop."""
        task = narration_screen()
        task.frame = frame_with_button(UNLIT)
        self.assertTrue(handle_dialogue(task))
        self.assertEqual(TOGGLE_POINT, task.tapped)
        self.assertEqual(TOGGLE_POINT, task.moved)
        self.assertIsNone(task.clicked)

    def test_the_button_gets_the_pointer_before_the_tap(self):
        """Upstream dwells on every button before clicking it, and this client drops a click that
        arrives without one."""
        task = narration_screen()
        task.frame = frame_with_button(UNLIT)
        handle_dialogue(task)
        self.assertEqual(2 * AFTER_TOGGLE, task.slept)

    def test_the_handler_taps_the_line_once_auto_advance_is_running(self):
        task = narration_screen()
        task.frame = frame_with_button(GLOW, MEASURED_GLOW)
        self.assertTrue(handle_dialogue(task))
        self.assertIsNotNone(task.clicked)
        self.assertIsNone(task.tapped)

    def test_a_button_that_will_not_turn_on_gives_way_to_tapping_the_line(self):
        """A live run tapped a button that never lit for over a minute and never advanced the line."""
        task = narration_screen()
        task.frame = frame_with_button(UNLIT)
        handle_dialogue(task)
        task.tapped = None
        self.assertTrue(handle_dialogue(task))
        self.assertIsNone(task.tapped)
        self.assertIsNotNone(task.clicked)

    def test_the_button_is_tried_again_once_the_retry_wait_has_passed(self):
        task = narration_screen()
        task.frame = frame_with_button(UNLIT)
        handle_dialogue(task)
        task.tapped = None
        setattr(task, TOGGLED_AT, getattr(task, TOGGLED_AT) - TOGGLE_RETRY)
        handle_dialogue(task)
        self.assertEqual(TOGGLE_POINT, task.tapped)

    def test_the_button_is_never_tapped_off_a_narration_screen(self):
        """The corner is only read once the screen has been recognised, so nothing else can be reached for."""
        task = option_screen()
        task.frame = frame_with_button(UNLIT)
        self.assertFalse(handle_dialogue(task))
        self.assertIsNone(task.tapped)


if __name__ == "__main__":
    unittest.main()
