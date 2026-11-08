"""Get a narration screen moving, which the Global client needs and no mode does.

Upstream's only tap-the-screen handler, `handle_close_page`, keys off the literal "点击屏幕". The Global client
prints no such prompt - its narration is a line of prose over a darkened frame, and an NPC talks in a speech
bubble over the scene - so nothing in Chaos or Sortie ever advances either, and upstream's stuck detector misses
them because its general random-click fallback is commented out.
"""

import random
import re
import time
from pathlib import Path

import numpy as np

from ok import Logger

from src.en.board import icon_match
from src.en.handlers import append, register
from src.en.screen import colour_share, frame_of, in_region, patch_of
from src.en.stuck import frozen_for

logger = Logger.get_logger(__name__)

# Shape alone was not enough: over the 702 captures in `captures/` it turned up 18 matches, 15 of them
# tooltips, tip banners and selection prompts, so the band and the box count below joined the rule, and the
# corpus then yields three matches, all prose. Every threshold's measurement is in `tests/TestDialogue.py`.
# Where narration sits, as `(left, top, right, bottom)` screen fractions. Measured prose runs 0.834 to 0.880
# top to bottom, and the button and tooltip rows that share the lower screen start at 0.908, so the band
# closes above one and below the other. The line also has to be near the middle to count.
NARRATION_REGION = (0.35, 0.80, 0.65, 0.90)
# How wide it has to be. Across the capture corpus prose measured 0.316 to 0.798, and the widest other line in
# the band was the Persona card picker's tip at 0.283, so this splits the two. A shorter line needs the arrow.
MIN_WIDTH = 0.30
# The down-pointing arrow narration draws in the bottom right corner once a line is waiting for a tap, cut from
# a 1080p frame. Three narration captures out of six show it, so it lets a short line in rather than being required.
ARROW_IMAGE = Path(__file__).with_name("images") / "advance_arrow.png"
# Where the arrow bobs, as `(left, top, right, bottom)` screen fractions. Its top edge measured 924 to 933 down at
# 1080p, and the keyboard hint drawn under it on PC starts at 977.
ARROW_REGION = (0.911, 0.833, 0.958, 0.903)
# The three captures showing the arrow scored 0.869 to 1.000, and the best of 846 others 0.570.
ARROW_MATCH = 0.75
# How much text a narration screen can carry. It dims the frame and hides the HUD, so the measured ones read
# three to six boxes. A screen busy enough to hold ten is showing something else and is not ours to tap.
MAX_TEXT_BOXES = 10
# How long the frame has to sit unchanged before a speech bubble is looked for. A bubble can be drawn anywhere
# over the scene, so its line has no band or width to be told apart by. The freeze is what says no other handler
# wanted the frame.
BUBBLE_AFTER_STUCK = 3
# Where a speech bubble can sit, as `(left, top, right, bottom)` screen fractions: under the HUD and above the
# party's feet. The stalled bubble's lines measured 0.356 and 0.394 down, and the button row starts at 0.908.
SPEECH_REGION = (0.0, 0.12, 1.0, 0.65)
# How many words a line needs to read as speech rather than a label. The stalled bubble's shorter line had five.
MIN_SPEECH_WORDS = 3
# A word, for counting them. Two letters or more, so a stray OCR fragment does not count as one.
WORD = re.compile(r"[A-Za-z']{2,}")
# Where a tap that advances the dialogue lands, picked at random inside this `(left, top, right, bottom)` box of
# screen fractions. A tap anywhere advances it, and the middle is scene art on every event screen captured, clear
# of the option cards from 0.78 down, the prompt above 0.30 and the magnifier one event draws at (0.60, 0.39).
TAP_AREA = (0.42, 0.42, 0.58, 0.58)
# How long a tap gets to land before the screen is read again. A tap either finishes drawing a line or moves to the next one.
BETWEEN_TAPS = 0.2
# The most taps one pass makes before handing the frame back, so a line that never advances cannot hold the run loop.
MAX_TAPS = 30
# The patch of frame the auto-advance button is drawn in, as `(left, top, right, bottom)` screen fractions.
# The ring measures 1660 to 1716 across and 30 to 86 down on a 1920x1080 capture.
TOGGLE_REGION = (0.865, 0.028, 0.894, 0.080)
# The middle of that button, where the tap turning it on lands.
TOGGLE_POINT = ((TOGGLE_REGION[0] + TOGGLE_REGION[2]) / 2, (TOGGLE_REGION[1] + TOGGLE_REGION[3]) / 2)
# The amber the ring and its chevrons glow in once auto-advance is running, as OpenCV HSV bounds. Hue is
# wide because the ring fades from gold at its brightest to a deep orange at its ends. Saturation goes down to
# 20 because a scene change washes the lit ring out to saturation ~25, while the off ring is white at ~2.
GLOW_LOW = np.array((10, 20, 120), dtype=np.uint8)
GLOW_HIGH = np.array((35, 255, 255), dtype=np.uint8)
# How much of the button's patch has to be amber to call auto-advance running. Over 779 captured frames every
# lit one measured 0.152 or more, the washed-out one 0.252, and all 23 showing it off 0.000.
MIN_GLOW = 0.05
# How much amber a ring needs before its chevrons are trusted. First speed measured 0.276 or more, and a fading button shows less.
MIN_FULL_GLOW = 0.2
# Each tap moves the button on one step: off, first speed, top speed, then back to off.
SPEED_OFF = "off"
SPEED_FIRST = "first speed"
# The right-hand chevron as `(left, top, right, bottom)` screen fractions, which is amber only at top speed and white only when off.
SECOND_CHEVRON = (0.8824, 0.0445, 0.8860, 0.0667)
# Amber share of that patch. Over 132 frames at first speed it read 0.083 at most, and 0.62 or more at top speed.
MIN_SECOND_GLOW = 0.3
# A pixel of the off chevron is at least this bright in every channel. Off filled 0.351 of the patch, against 0.244 for white text
# and 0.137 at most for the padlock and struck-through looks. A fade to black reads 0.
OFF_WHITE = 150
MIN_OFF_WHITE = 0.3
# How long the button gets to notice the pointer, and then to redraw before the corner is read again. The
# hover matters: upstream taps every button this way and the client can drop a click that arrives without one.
AFTER_TOGGLE = 0.5
# How long after tapping the button to keep tapping the prose instead of tapping the button again. Some screens
# draw the button but never let it turn on, and tapping it again every frame left one run on the same line for
# over a minute. Long enough to carry a whole cutscene, short enough that the next one tries the button again.
TOGGLE_RETRY = 30
# Where a memory cutscene shows, as `(left, top, right, bottom)` screen fractions: the middle of the scene, clear of the HUD and the prose.
MEMORY_REGION = (0.1, 0.25, 0.9, 0.75)
# A memory cutscene is drawn in greyscale and draws its auto-advance button but ignores it. Colour is any pixel past this saturation.
COLOURED_LOW = np.array((0, 41, 0), dtype=np.uint8)
COLOURED_HIGH = np.array((179, 255, 255), dtype=np.uint8)
# The 11:31 memory cutscene measured 0.015 coloured at brightness 131. The 847 captures held no narration under 0.12, and the black
# test frames sit under the brightness floor.
MAX_MEMORY_COLOUR = 0.05
MIN_MEMORY_BRIGHTNESS = 80
# The stroke across a locked button, as two `(x, y)` screen fractions, and the points read along it. 22 taps on it over three runs changed nothing.
LOCK_STROKE = ((0.8714, 0.0630), (0.8870, 0.0435))
LOCK_POINTS = 21
# A point on the stroke is white in every channel. At least 0.71 of them were over 400 locked frames, and 0.52 at most on the lit button and the rest.
LOCK_WHITE = 170
MIN_LOCK_WHITE = 0.6
# Set on the task: when the button was last tapped and what it read then, so a tap that did not take is not repeated every frame.
TOGGLED_AT = "_en_auto_advance_toggled_at"
TOGGLED_FROM = "_en_auto_advance_toggled_from"
# A handler Chaos and Sortie both carry and Story does not, which is how the tap reaches those two alone.
MODE_ANCHOR = "handle_event_task"

_patched = False


def narration_line(task):
    """Find the line of prose on a narration screen, if this is one.

    Shape rather than content, because the text is different every time and the reader has nothing else to go
    on. Any qualifying line will do, since the tap that follows goes to the middle of the screen, not the line.

    Args:
        task: The running task, holding the current OCR pass and capture.

    Returns:
        The narration box, or None when this screen is not one.
    """
    lines = [box for box in task.all_texts if box.name.strip() and in_region(box, NARRATION_REGION, task.width, task.height)]
    wide = next((box for box in lines if box.width / task.width >= MIN_WIDTH), None)
    if wide is not None or not lines:
        return wide
    return lines[0] if advance_arrow_showing(task) else None


def advance_arrow_showing(task):
    """Report whether the game is drawing the arrow that says a narration line is waiting for a tap.

    Args:
        task: The running task, whose `frame` holds the current capture.

    Returns:
        True when the arrow is in the corner. False when it is not, or there is no frame to read.
    """
    frame = frame_of(task)
    patch = patch_of(frame, ARROW_REGION)
    if patch is None or patch.size == 0:
        return False
    return icon_match(patch, ARROW_IMAGE, frame.shape[0]) >= ARROW_MATCH


def speech_line(task):
    """Find a line of an NPC's speech bubble, on a frame nothing else has claimed for a while.

    Args:
        task: The running task, holding the current OCR pass and upstream's stuck clock.

    Returns:
        The first speech line, or None when the frame has not been frozen long enough or holds none.
    """
    frozen = frozen_for(task)
    if frozen is None or frozen < BUBBLE_AFTER_STUCK:
        return None
    for box in task.all_texts:
        if in_region(box, SPEECH_REGION, task.width, task.height) and len(WORD.findall(box.name)) >= MIN_SPEECH_WORDS:
            return box
    return None


def speed_to_raise(task):
    """Say which speed the auto-advance button is at when another tap would make it faster.

    Args:
        task: The running task, whose `frame` holds the current capture.

    Returns:
        `SPEED_OFF` or `SPEED_FIRST`, or None for anything else: top speed, where a tap wraps back to off, a fade,
        a locked button, no button, or a frame that cannot be read.
    """
    frame = frame_of(task)
    button = patch_of(frame, TOGGLE_REGION)
    chevron = patch_of(frame, SECOND_CHEVRON)
    if button is None or chevron is None or button.size == 0 or chevron.size == 0:
        return None
    glow = colour_share(button, GLOW_LOW, GLOW_HIGH)
    if glow < MIN_GLOW:
        return SPEED_OFF if float(np.mean(chevron.min(axis=2) >= OFF_WHITE)) >= MIN_OFF_WHITE else None
    return SPEED_FIRST if glow >= MIN_FULL_GLOW and colour_share(chevron, GLOW_LOW, GLOW_HIGH) < MIN_SECOND_GLOW else None


def memory_scene(task):
    """Report whether the frame is a greyscale memory cutscene, whose auto-advance button is locked.

    Args:
        task: The running task, whose `frame` holds the current capture.

    Returns:
        True when the middle of the scene is bright and all but colourless.
    """
    patch = patch_of(frame_of(task), MEMORY_REGION)
    if patch is None or patch.size == 0:
        return False
    return patch.mean() >= MIN_MEMORY_BRIGHTNESS and colour_share(patch, COLOURED_LOW, COLOURED_HIGH) < MAX_MEMORY_COLOUR


def button_locked(task):
    """Report whether the auto-advance button is struck through, which means a tap on it does nothing.

    Args:
        task: The running task, whose `frame` holds the current capture.

    Returns:
        True when the stroke is drawn. A frame that cannot be read counts as not locked.
    """
    frame = frame_of(task)
    if frame is None or frame.size == 0:
        return False
    height, width = frame.shape[:2]
    (left, top), (right, bottom) = LOCK_STROKE
    white = [frame[int((top + (bottom - top) * step) * height), int((left + (right - left) * step) * width)][:3].min() >= LOCK_WHITE for step in np.linspace(0, 1, LOCK_POINTS)]
    locked = float(np.mean(white)) >= MIN_LOCK_WHITE
    if locked:
        logger.debug("auto-advance button is locked, so the line is tapped instead")
    return locked


def raise_speed(task, speed):
    """Tap the auto-advance button so the game plays the rest of the cutscene itself, one level faster.

    Args:
        task: The running task.
        speed: The level `speed_to_raise` read, which the tap moves on from.
    """
    task.log_info(f"dialogue with auto-advance at {speed}, tapping it faster")
    setattr(task, TOGGLED_AT, time.monotonic())
    setattr(task, TOGGLED_FROM, speed)
    task.move_relative(*TOGGLE_POINT)
    task.sleep(AFTER_TOGGLE)
    task.click(*TOGGLE_POINT, after_sleep=AFTER_TOGGLE)


def handle_dialogue(task):
    """Advance narration or a speech bubble, by the game's own auto-advance where that can be reached and a tap where it cannot.

    Args:
        task: The running task.

    Returns:
        True when the screen was acted on, which claims the frame.
    """
    # A busy screen is checked once here, since it rules out both kinds of line.
    if not task.all_texts or len(task.all_texts) > MAX_TEXT_BOXES:
        return False
    line = narration_line(task) or speech_line(task)
    if line is None:
        return False
    speed = speed_to_raise(task)
    # Only a tap that left the button where it was has to wait, so off still climbs straight to top speed.
    moved_on = speed != getattr(task, TOGGLED_FROM, None)
    retry_due = time.monotonic() - getattr(task, TOGGLED_AT, float("-inf")) >= TOGGLE_RETRY
    if speed is not None and (moved_on or retry_due) and not memory_scene(task) and not button_locked(task):
        raise_speed(task, speed)
        return True
    tap_through(task, line)
    return True


def tap_through(task, line):
    """Tap the middle of the screen, then keep tapping for as long as it still reads as narration.

    The screen is read again between taps here rather than left to the run loop, which only reads it once a second.

    Args:
        task: The running task.
        line: The line on screen, from `narration_line` or `speech_line`, which is logged rather than tapped.
    """
    left, top, right, bottom = TAP_AREA
    for _ in range(MAX_TAPS):
        task.log_info(f"dialogue, tapping to advance: {line.name}")
        task.click(random.uniform(left, right), random.uniform(top, bottom), after_sleep=BETWEEN_TAPS)
        task.all_texts = task.ocr()
        line = narration_line(task) if len(task.all_texts) <= MAX_TEXT_BOXES else None
        if line is None:
            return


def apply():
    """Give Chaos and Sortie a way past the narration screens nothing else advances.

    Appended last, after everything that recognises a screen by name, which is what keeps an immediate tap safe.
    """
    global _patched
    if _patched:
        return
    register(lambda: append(handle_dialogue, MODE_ANCHOR))
    _patched = True
