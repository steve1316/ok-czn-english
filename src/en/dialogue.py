"""Get a narration screen moving, which the Global client needs and no mode does.

Upstream's only tap-the-screen handler, `handle_close_page`, keys off the literal "点击屏幕". The Global client
prints no such prompt - a narration screen there is a line of prose over a darkened frame with a small caret
in the corner - so nothing in Chaos or Sortie ever advances one. `ChaosMode.description` asks the user to turn
the game's own auto-story on instead, which covers it when the setting is found and does nothing when it is not.

A logged run shows what that costs. The bot reached "The Soldier's eyes are fixed on the group." at 14:26:39
and never left: upstream's stuck detector fired at ten seconds and worked through its fallbacks - the close
button, the secret enemy, card recognition - each of which missed, because its general random-click fallback
is commented out. The run sat there for 200 more frames until it was stopped by hand.

The reader gets almost nothing to work with on that screen. The whole OCR pass was the health bar, the credit
count and the prose, so the line's shape is the only signal available: wide, horizontally centred, and low.
Width is what separates it from an event option, whose text sits in the same band and is centred in the same
place but is a third as wide.

Shape alone was not enough. Running this over the 702 captures in `captures/` turned up 18 matches, of which
15 were tooltips, tip banners and selection prompts rather than prose - so two things the corpus measured are
part of the rule. Narration sits at 0.834 to 0.880 while those rows sit at 0.908 and below, which is what
`NARRATION_REGION` draws the line on. And a narration screen darkens the frame and takes the HUD down with it,
so it carries three to six readable boxes where a tip banner's screen carries seventeen to fifty-six - which
is what `MAX_TEXT_BOXES` is for. With both, the corpus yields three matches and all three are prose.

The measurements behind every threshold are in `tests/TestDialogue.py`.

Tapping every line is not the cheapest way through, though. The game advances narration by itself when its
auto-advance setting is on, and the button for it sits in the top right corner of the same screen - a ring
drawn white with a padlock through it while it is off, and in amber once it is running. One tap on that
plays the rest of the cutscene out without the bot in the loop, so `handle_dialogue` reaches for it first
and only taps the prose when auto-advance is already going.

Amber is the whole reading. Across twenty captured frames the button's patch is 10.5% to 15.0% amber every
time it is running and 0.0% every time it is off, so nothing finer than a colour share is needed. A screen
that draws no button at all reads the same as one drawn off, and the tap that follows then lands on empty
space in the top corner - which on a narration screen advances the line, which is what the handler was
about to do anyway.

That ambiguity is why the button is only read once `narration_line` has recognised the screen. It also
caps what the button can do: a narration screen the shape rule misses gets no tap and no toggle either,
so this makes a recognised cutscene cheaper rather than widening what is recognised.

The handler runs last, after the ones that recognise a screen by name. That ordering is what keeps an
immediate tap safe: a frame only reaches here once nothing else has claimed it.

Chaos and Sortie get it, and Story does not. Story has its own skip and auto-dialogue handlers, and none of
the screens measured here came from it, so it is left as it was rather than given a handler tuned on another
mode's captures. `handle_event_task` is what picks the two out: both carry it and Story does not.
"""

import numpy as np

from ok import Logger

from src.en.handlers import append, register
from src.en.screen import colour_share, frame_of, in_region, patch_of

logger = Logger.get_logger(__name__)

# Where narration sits, as `(left, top, right, bottom)` screen fractions. Measured prose runs 0.834 to 0.880
# top to bottom, and the button and tooltip rows that share the lower screen start at 0.908, so the band
# closes above one and below the other. The line also has to be near the middle to count.
NARRATION_REGION = (0.35, 0.80, 0.65, 0.90)
# How wide it has to be. Narration measured 0.51 to 0.72 and an option card's text 0.17, so this sits clear
# of both rather than just past one of them.
MIN_WIDTH = 0.35
# How much text a narration screen can carry. It dims the frame and hides the HUD, so the measured ones read
# three to six boxes. A screen busy enough to hold ten is showing something else and is not ours to tap.
MAX_TEXT_BOXES = 10
# Long enough for the next line to be drawn before the screen is read again.
AFTER_TAP = 0.5
# The patch of frame the auto-advance button is drawn in, as `(left, top, right, bottom)` screen fractions.
# The ring measures 1660 to 1716 across and 30 to 86 down on a 1920x1080 capture.
TOGGLE_REGION = (0.865, 0.028, 0.894, 0.080)
# The middle of that button, where the tap turning it on lands.
TOGGLE_POINT = ((TOGGLE_REGION[0] + TOGGLE_REGION[2]) / 2, (TOGGLE_REGION[1] + TOGGLE_REGION[3]) / 2)
# The amber the ring and its chevrons glow in once auto-advance is running, as OpenCV HSV bounds. Hue is
# wide because the ring fades from gold at its brightest to a deep orange at its ends.
GLOW_LOW = np.array((10, 90, 120), dtype=np.uint8)
GLOW_HIGH = np.array((35, 255, 255), dtype=np.uint8)
# How much of the button's patch has to be amber to call auto-advance running. It measured 0.105 to 0.150
# on every frame showing it on and 0.000 on every frame showing it off, so this sits clear of both.
MIN_GLOW = 0.05
# How long the button gets to notice the pointer, and then to redraw before the corner is read again. The
# hover matters: upstream taps every button this way and the client can drop a click that arrives without one.
AFTER_TOGGLE = 0.5
# A handler Chaos and Sortie both carry and Story does not, which is how the tap reaches those two alone.
MODE_ANCHOR = "handle_event_task"

_patched = False


def narration_line(task):
    """Find the line of prose on a narration screen, if this is one.

    Shape rather than content, because the text is different every time and the reader has nothing else to go
    on. Any qualifying line will do, since a tap anywhere on the screen advances it.

    Args:
        task: The running task, holding the current OCR pass.

    Returns:
        The narration box, or None when this screen is not one.
    """
    boxes = task.all_texts or []
    if len(boxes) > MAX_TEXT_BOXES:
        return None
    for box in boxes:
        if not box.name.strip() or box.width / task.width < MIN_WIDTH:
            continue
        if in_region(box, NARRATION_REGION, task.width, task.height):
            return box
    return None


def auto_advance_off(task):
    """Report whether the game has been left to be tapped through a line at a time.

    Args:
        task: The running task, whose `frame` holds the current capture.

    Returns:
        True when the button is there to be turned on. A frame that cannot be read counts as on, so a
        reading that fails leaves the tap doing the work rather than putting a click somewhere unasked.
    """
    patch = patch_of(frame_of(task), TOGGLE_REGION)
    if patch is None or patch.size == 0:
        return False
    return colour_share(patch, GLOW_LOW, GLOW_HIGH) < MIN_GLOW


def turn_auto_advance_on(task):
    """Tap the auto-advance button so the game plays the rest of the cutscene itself.

    Args:
        task: The running task.
    """
    task.log_info("narration screen with auto-advance off, turning it on")
    task.move_relative(*TOGGLE_POINT)
    task.sleep(AFTER_TOGGLE)
    task.click(*TOGGLE_POINT, after_sleep=AFTER_TOGGLE)


def handle_dialogue(task):
    """Advance a narration screen, by the game's own auto-advance where that can be reached and a tap where it cannot.

    Args:
        task: The running task.

    Returns:
        True when the screen was acted on, which claims the frame.
    """
    line = narration_line(task)
    if line is None:
        return False
    if auto_advance_off(task):
        turn_auto_advance_on(task)
        return True
    task.log_info(f"narration screen, tapping to advance: {line.name}")
    task.click_box(line)
    task.sleep(AFTER_TAP)
    return True


def apply():
    """Give Chaos and Sortie a way past the narration screens nothing else advances."""
    global _patched
    if _patched:
        return
    register(lambda: append(handle_dialogue, MODE_ANCHOR))
    _patched = True
