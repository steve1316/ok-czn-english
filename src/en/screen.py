"""Read positions off the screen the way the handlers talk about them.

Handlers here describe a place as a `(left, top, right, bottom)` box in screen fractions, which is the same
shape upstream uses for `task.box_of_screen` and for its own region literals. The reader hands back pixels,
so something has to convert, and doing it inline is how the same four lines of arithmetic ended up copied
across several modules.

`text_in_region` is the loop those modules actually want. Almost every fork-local handler starts by asking
"is this caption in that band", and writing the walk out per module is how near-identical copies of it keep
appearing next to the copies of the arithmetic.

The screen literals two or more modules share live here too, for the same reason. `find_box_at_point` has no
tolerance at all, so a point that upstream nudges and the fork updates in only one of its copies does not
fail - it silently reads nothing, forever.

Reading raw pixels is the other half of it. Three modules now judge a patch of frame by its colour -
`src/en/board.py` for Action Points and Ego costs, `src/en/pins.py` for a build preset's pin, and
`src/en/dialogue.py` for the auto-advance button - and every one of them wants the same four steps: take
the frame, cut a relative box out of it, convert to HSV, count what falls inside a pair of bounds. Those
four live here now so the next colour reading is a call rather than a fourth copy.
"""

import cv2
import numpy as np

# Where the Combatants tab writes each team member's name. Upstream's own numbers, from the read inside
# `handle_archive_target_member`. Both `src/en/navigation.py` and `src/en/rewards.py` work from them.
COMBATANT_NAME_POINTS = ((0.159, 0.368), (0.432, 0.368), (0.705, 0.369))


def in_region(box, region, width, height):
    """Report whether a box's centre sits inside a relative region.

    The centre rather than the whole box, so a line of text that overruns a band's edge still counts as being
    in it. Upstream's `in_boundary` tests full containment, which drops exactly the wide boxes worth finding.

    Args:
        box: The OCR box.
        region: A `(left, top, right, bottom)` tuple in screen fractions.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        True when the box centre is inside the region.
    """
    left, top, right, bottom = region
    center_x = (box.x + box.width / 2) / width
    center_y = (box.y + box.height / 2) / height
    return left <= center_x <= right and top <= center_y <= bottom


def text_in_region(task, needle, region):
    """Find the first OCR box in a region whose text contains a caption.

    Case is ignored, which costs nothing on the Chinese literals the catalog produces and saves the callers
    that read English straight off the screen from spelling the fold out themselves.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        needle: The caption to look for, matched as a substring.
        region: A `(left, top, right, bottom)` tuple in screen fractions.

    Returns:
        The matching box, or None when the caption is not in that part of the screen.
    """
    wanted = needle.casefold()
    for box in getattr(task, "all_texts", None) or []:
        if wanted in box.name.casefold() and in_region(box, region, task.width, task.height):
            return box
    return None


def frame_of(task):
    """Take the frame to read, once, for the whole of one answer.

    Reached through the task, `frame` waits out a pause and re-captures once the last frame has been let go,
    so asking for it twice inside one reading can quietly mix two frames' pixels into a single answer.

    Args:
        task: The running task.

    Returns:
        The frame, or None when there is none to read.
    """
    return getattr(task, "frame", None)


def patch_of(frame, box):
    """Cut a relative box out of a frame.

    Args:
        frame: The frame to cut from, or None when there is none.
        box: A `(left, top, right, bottom)` tuple in fractions of the frame.

    Returns:
        The pixels inside the box, colour channels only, or None when there is no frame or the box runs off
        it. A box that falls partly outside would otherwise come back as a narrow strip of whatever sits at
        the edge, which reads as a perfectly confident answer about the wrong pixels.
    """
    if frame is None:
        return None
    left, top, right, bottom = box
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        return None
    height, width = frame.shape[:2]
    return frame[int(top * height):int(bottom * height), int(left * width):int(right * width), :3]


def hsv_of(patch):
    """Turn a patch into the colour space every reading here judges it in.

    Args:
        patch: The pixels to convert, in BGR.

    Returns:
        The patch in HSV, or None when there is nothing to convert.
    """
    if patch is None or patch.size == 0:
        return None
    return cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)


def colour_share(patch, low, high):
    """Say how much of a patch is drawn in one band of colour.

    Args:
        patch: The pixels to measure, in BGR.
        low: The lower HSV bound, as an OpenCV array.
        high: The upper HSV bound.

    Returns:
        The share of pixels inside those bounds, from 0 to 1, and 0 for a patch there is nothing to read.
    """
    hsv = hsv_of(patch)
    if hsv is None:
        return 0.0
    inside = cv2.inRange(hsv, low, high)
    return float(np.count_nonzero(inside)) / inside.size
