"""Tap a narration screen to advance it, which the Global client needs and no mode does.

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

The handler runs last, after the ones that recognise a screen by name. That ordering is what keeps an
immediate tap safe: a frame only reaches here once nothing else has claimed it.

Chaos and Sortie get it, and Story does not. Story has its own skip and auto-dialogue handlers, and none of
the screens measured here came from it, so it is left as it was rather than given a handler tuned on another
mode's captures. `handle_event_task` is what picks the two out: both carry it and Story does not.
"""

from ok import Logger

from src.en.handlers import append, register
from src.en.screen import in_region

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


def handle_dialogue(task):
    """Advance a narration screen by tapping it.

    Args:
        task: The running task.

    Returns:
        True when the screen was tapped, which claims the frame.
    """
    line = narration_line(task)
    if line is None:
        return False
    task.log_info(f"narration screen, tapping to advance: {line.name}")
    task.click_box(line)
    task.sleep(AFTER_TAP)
    return True


def apply():
    """Give Chaos and Sortie a last-resort tap for the narration screens nothing else advances."""
    global _patched
    if _patched:
        return
    register(lambda: append(handle_dialogue, MODE_ANCHOR))
    _patched = True
