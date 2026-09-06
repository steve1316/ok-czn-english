"""Read what the battle screen says about the moment a card is being chosen in.

`SortieMode.run` pays for one full-frame OCR a second and every handler reads the result for free, so anything
here has to come out of that pass or out of raw pixels. Nothing in this module runs OCR.

Action Points are the first thing it reads, and they are read from colour rather than from text. The readout
is a single large digit above the hand counter, and the OCR engine does not return a box for it at all - not
in a full frame, and not on a tight upscaled crop either, which was checked before settling for this. What
the game does give away is how it draws the digit: bright blue with a glow while there are points to spend,
and a thin grey outline once there are none. Counting how much of that small patch is lit tells the two apart
without reading anything.

The figures behind `LIT_ENOUGH`: across 30 real frames - 25 with no points left, 5 with points - the lit
share came out at most 0.031 for an empty readout and at least 0.130 for a full one, a gap of four times over,
and it holds at every resolution the app supports from 1280x720 to 2560x1440. The threshold sits between the
two with room on both sides. `tests/TestBoard.py` pins the tightest pair of those frames, so anything that
narrows the gap fails there first.

`LIT` is 200 rather than the more obvious 170 because one frame's background sits at exactly 170 across a
large flat area, and counting that would have read an empty turn as a full one.

This says whether any points remain, not how many. That is enough for the planner, which only needs to know
whether a card costing something can still be played, and it is all the screen actually gives away.
"""

import cv2
import numpy as np

# The Action Point readout, as a relative box. Deliberately tight on the digit: the hand counter below it and
# the decorative line through its middle both sit outside, so neither can be counted as a lit reading.
ACTION_POINTS = (0.488, 0.898, 0.528, 0.948)
# How bright a pixel has to be to count as part of the digit rather than the scene behind it. Comfortably
# above the flat grey a UI panel is drawn in, so a panel can never be mistaken for a lit readout.
LIT = 200
# The share of the readout that has to be lit before it is read as "points remain". See the module docstring
# for the readings this sits between.
LIT_ENOUGH = 0.08


def patch_of(task, box):
    """Cut a relative box out of the frame being looked at.

    Args:
        task: The running task.
        box: A `(left, top, right, bottom)` tuple in fractions of the frame.

    Returns:
        The pixels inside the box, or None when there is no frame to read.
    """
    frame = getattr(task, "frame", None)
    if frame is None:
        return None
    height, width = frame.shape[:2]
    left, top, right, bottom = box
    return frame[int(top * height):int(bottom * height), int(left * width):int(right * width)]


def lit_fraction(patch):
    """Say how much of a patch is drawn brightly.

    Args:
        patch: The pixels to measure, in BGR.

    Returns:
        The share of pixels brighter than `LIT`, from 0 to 1, and 0 for an empty patch.
    """
    if patch is None or patch.size == 0:
        return 0.0
    grey = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float(np.count_nonzero(grey > LIT)) / grey.size


def has_action_points(task):
    """Say whether the turn still has Action Points to spend.

    Args:
        task: The running task.

    Returns:
        True while the readout is lit. Also True when there is no frame to read, because ending a turn that
        had not finished costs more than trying a card that will not play.
    """
    patch = patch_of(task, ACTION_POINTS)
    if patch is None:
        return True
    return lit_fraction(patch) >= LIT_ENOUGH
