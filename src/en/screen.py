"""Read positions off the screen the way the handlers talk about them.

Handlers describe a place as a `(left, top, right, bottom)` box in screen fractions, the same shape upstream
uses for `task.box_of_screen` and its own region literals. The reader hands back pixels, so something has to
convert, and doing it inline is how the same four lines of arithmetic ended up copied across several modules.
"""

import cv2
import numpy as np

from src.en.handlers import standing_in

# Where the Combatants tab writes each team member's name. Upstream's own numbers, from the read inside
# `handle_archive_target_member`. `combatant_names` is the read every caller wanted, so they share it.
COMBATANT_NAME_POINTS = ((0.159, 0.368), (0.432, 0.368), (0.705, 0.369))
# Where the information page and All Piles both draw their X, the tap upstream's team capture closes the page with.
PAGE_CLOSE = (0.960, 0.054)
# Where that same screen frames each of a combatant's three equipment slots, as an offset from their name's x
# and an absolute y. Measured off the captured screen: the tiles are 92px wide, pitched 156px, and the band
# sampled is the 20px of plain frame colour above the item art, between the tile's top edge and the icon.
COMBATANT_SLOT_OFFSETS = (0.0316, 0.1129, 0.1941)
COMBATANT_SLOT_Y = 0.856
# What `white_mask` counts as the white strokes of an icon.
WHITE_MAX_SATURATION = 60
WHITE_MIN_VALUE = 200


def combatant_names(task, utils):
    """Read the team's three names off the Combatants screen.

    Args:
        task: The running task, whose current OCR pass the names are taken from.
        utils: The loaded `utils` module, for its point reader.

    Returns:
        One name per column, left to right, blank where the column could not be read. Positional rather than
        packed, because the equipment slots below a column are matched to it by position.
    """
    names = []
    for x, y in COMBATANT_NAME_POINTS:
        box = utils.find_box_at_point(task, x, y)
        names.append(box.name.strip() if box else "")
    return names


def combatant_slot_points(column):
    """Give the three points to sample one combatant's equipment slots at.

    Args:
        column: Which combatant, 0 to 2, counted left to right.

    Returns:
        Three `(x, y)` points in screen fractions, in slot order.
    """
    name_x = COMBATANT_NAME_POINTS[column][0]
    return tuple((name_x + offset, COMBATANT_SLOT_Y) for offset in COMBATANT_SLOT_OFFSETS)


def centre_of(box, width, height):
    """Give a box's centre as fractions of the screen.

    Args:
        box: The OCR box.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        An `(x, y)` pair.
    """
    return (box.x + box.width / 2) / width, (box.y + box.height / 2) / height


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
    center_x, center_y = centre_of(box, width, height)
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


def same_line(above, box):
    """Say whether a box sits on the same line of text as one above it rather than on the line below.

    The two lines of a wrapped shelf name come back boxed a few pixels into each other - Instant over Judgment by 1,
    Bottomless over Hunger by 3 - so only a box starting in the top half of the other counts as the same line.

    Args:
        above: The box nearer the top of the screen.
        box: The box being placed.

    Returns:
        True when `box` starts within the top half of `above`.
    """
    return box.y < above.y + above.height / 2


def lines_in(task, region):
    """Read a region's text a line at a time, top to bottom and left to right, with a space between the parts.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: A `(left, top, right, bottom)` tuple in screen fractions.

    Returns:
        The text, or an empty string when nothing is in the region.
    """
    boxes = [box for box in getattr(task, "all_texts", None) or [] if box.name.strip() and in_region(box, region, task.width, task.height)]
    lines = []
    for box in sorted(boxes, key=lambda box: box.y):
        if lines and same_line(lines[-1][0], box):
            lines[-1].append(box)
        else:
            lines.append([box])
    return " ".join(box.name.strip() for line in lines for box in sorted(line, key=lambda box: box.x))


def raw_ocr(task, box=None):
    """Read the screen in the English the client draws.

    `ocr.po` would rewrite a lone "Damage" or "Shield" line into the Chinese a handler looks for.

    Args:
        task: The running task.
        box: The part of the screen to read, or None for all of it.
    """
    with standing_in(task.executor, ocr_po_translation=None):
        task.all_texts = task.ocr(box=box)


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


def white_mask(patch):
    """Keep only the near-white pixels of a patch, so an icon matches whatever it is drawn over.

    Args:
        patch: The pixels to reduce, in BGR.

    Returns:
        A single-channel image, 255 where the pixel is near white and 0 elsewhere.
    """
    return cv2.inRange(hsv_of(patch), (0, 0, WHITE_MIN_VALUE), (180, WHITE_MAX_SATURATION, 255))


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
