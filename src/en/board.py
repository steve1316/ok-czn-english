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

The Ego panel is read the same way. Each of the three slots carries a cost badge, drawn blue while the EP bar
can pay for it and flat grey once it cannot, so which Ego skills are actually available is a colour question
too. Measured over 30 badges, an affordable one is at least 21% blue and one that cannot be paid for is
exactly 0% at every supported resolution - the widest margin anything here is judged on.

The attribute an enemy is weak to is read the same way again. Each enemy carries a small coloured badge just
below and right of its action counter, and the colour is the attribute: the client stores attributes as
colours in the first place, so `ATTRIBUTES` already says which is which. Only the orange one has been checked
against the game - it is Instinct - but the rest come from the client's own table rather than from guesswork.
The badge hues measured so far sit far apart, at 15, 78 and 133 out of 180, with a spread of about three each.

Enemies are found by their action counter, a magenta diamond of a consistent size, and the badge is taken at
a fixed offset from it. When the enemies disagree the answer is that there is no preference, since nothing a
single card does would exploit all of them, and no capture so far shows a mixed fight to check anything
cleverer against.
"""

import cv2
import numpy as np

from src.en.game_battle import ATTRIBUTES

# The Action Point readout, as a relative box. Deliberately tight on the digit: the hand counter below it and
# the decorative line through its middle both sit outside, so neither can be counted as a lit reading.
ACTION_POINTS = (0.488, 0.898, 0.528, 0.948)
# How bright a pixel has to be to count as part of the digit rather than the scene behind it. Comfortably
# above the flat grey a UI panel is drawn in, so a panel can never be mistaken for a lit readout.
LIT = 200
# The share of the readout that has to be lit before it is read as "points remain". See the module docstring
# for the readings this sits between.
LIT_ENOUGH = 0.08

# The three Ego slots, in the order the panel shows them.
EGO_KEYS = ("F1", "F2", "F3")
# Where each slot's cost badge sits. The three are evenly spaced down the panel, and the figures come from the
# OCR pass, which does read the bottom slot's badge and both of the outer labels even though it misses the
# Action Point digit entirely.
EGO_BADGE_X = 0.065
EGO_BADGE_Y = {"F1": 0.7140, "F2": 0.8050, "F3": 0.8960}
EGO_BADGE_HALF = (0.0090, 0.0150)
# What the game paints an affordable badge: its own UI blue, well clear of the grey a spent one is drawn in.
BLUE_HUE = (95, 125)
BLUE_SATURATION = 80
BLUE_VALUE = 120
# How much of a badge has to be that blue before the Ego behind it is treated as one that can be fired.
EGO_READY = 0.10

# Where the enemies' counters and badges are drawn: below the top HUD, above the cards and the combatants.
ENEMY_BAND = (0.30, 0.12, 1.00, 0.60)
# The action counter's own magenta, and the shape it is drawn in. The HP bar beside it is a lighter pink and
# is far too wide to pass the squareness test, so neither can be mistaken for the other.
COUNTER_HUE = (160, 178)
COUNTER_SATURATION = 170
COUNTER_VALUE = 120
COUNTER_MIN_AREA = 400
COUNTER_SQUARENESS = (0.6, 1.7)
# How tall a counter is, as a share of the frame. Every real one measures between 0.057 and 0.060, while
# the magenta flashes an attack throws up run from 0.08 to 0.38 and the smaller markers sit at 0.033, so
# this band is what keeps a hit landing on screen from being counted as another enemy.
COUNTER_HEIGHT = (0.045, 0.072)
# Where the attribute badge sits relative to its counter, and how much of it to sample.
BADGE_OFFSET = (0.0185, 0.0225)
BADGE_HALF = (0.0085, 0.0085)
BADGE_SATURATION = 150
BADGE_VALUE = 130
# How much of the sampled patch has to be strongly coloured before it is read as a badge rather than scenery.
BADGE_ENOUGH = 0.20
# The hue the client draws each of its attribute colours in. Red sits at 0 rather than 180 only because that
# is the same place on a hue wheel, and the nearest of these five decides which attribute a badge is.
ATTRIBUTE_HUES = {"RED": 0, "ORANGE": 15, "GREEN": 78, "BLUE": 110, "PURPLE": 133}
# How far a badge's hue may sit from the nearest of those before it is treated as not a badge at all.
HUE_TOLERANCE = 20


def patch_of(task, box):
    """Cut a relative box out of the frame being looked at.

    Args:
        task: The running task.
        box: A `(left, top, right, bottom)` tuple in fractions of the frame.

    Returns:
        The pixels inside the box, or None when there is no frame to read or the box runs off it. A box that
        falls partly outside would otherwise come back as a narrow strip of whatever sits at the edge, which
        reads as a perfectly confident answer about the wrong pixels.
    """
    frame = getattr(task, "frame", None)
    if frame is None:
        return None
    left, top, right, bottom = box
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        return None
    height, width = frame.shape[:2]
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


def blue_fraction(patch):
    """Say how much of a lit patch is drawn in the game's own UI blue.

    Measured against the lit pixels rather than the whole patch, so a badge sitting on a dark background and
    one sitting on a bright scene are judged the same way.

    Args:
        patch: The pixels to measure, in BGR.

    Returns:
        The blue share of the lit pixels, from 0 to 1, and 0 for an empty patch.
    """
    if patch is None or patch.size == 0:
        return 0.0
    hue, saturation, value = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
    lit = value > BLUE_VALUE
    blue = lit & (saturation > BLUE_SATURATION) & (hue > BLUE_HUE[0]) & (hue < BLUE_HUE[1])
    return float(np.count_nonzero(blue)) / max(int(np.count_nonzero(lit)), 1)


def affordable_egos(task):
    """List the Ego skills the EP bar can currently pay for.

    Args:
        task: The running task.

    Returns:
        The keys that fire an affordable Ego, in panel order. Empty when none can be paid for, and empty when
        there is no frame to read, since firing one blind is the behaviour this exists to replace.
    """
    half_x, half_y = EGO_BADGE_HALF
    ready = []
    for key in EGO_KEYS:
        centre = EGO_BADGE_Y[key]
        box = (EGO_BADGE_X - half_x, centre - half_y, EGO_BADGE_X + half_x, centre + half_y)
        if blue_fraction(patch_of(task, box)) > EGO_READY:
            ready.append(key)
    return ready


def hue_distance(one, other):
    """Measure the gap between two hues the short way round the wheel.

    Args:
        one: A hue, 0 to 179.
        other: The hue to compare it against.

    Returns:
        The smaller of the two ways round, so red at 179 and red at 0 are neighbours rather than opposites.
    """
    gap = abs(int(one) - int(other)) % 180
    return min(gap, 180 - gap)


def attribute_of(patch):
    """Say which attribute a badge is drawn for.

    Args:
        patch: The pixels the badge was sampled from, in BGR.

    Returns:
        The attribute's name, or None when the patch holds no badge worth reading.
    """
    if patch is None or patch.size == 0:
        return None
    hue, saturation, value = cv2.split(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV))
    strong = (saturation > BADGE_SATURATION) & (value > BADGE_VALUE)
    if np.count_nonzero(strong) < BADGE_ENOUGH * strong.size:
        return None
    middle = int(np.median(hue[strong]))
    colour = min(ATTRIBUTE_HUES, key=lambda name: hue_distance(middle, ATTRIBUTE_HUES[name]))
    if hue_distance(middle, ATTRIBUTE_HUES[colour]) > HUE_TOLERANCE:
        return None
    return ATTRIBUTES.get(colour)


def enemy_counters(task):
    """Find the action counter of every enemy on screen.

    Args:
        task: The running task.

    Returns:
        A list of `(x, y)` centres in fractions of the frame, left to right.
    """
    band = patch_of(task, ENEMY_BAND)
    if band is None or band.size == 0:
        return []
    frame = task.frame
    height, width = frame.shape[:2]
    hue, saturation, value = cv2.split(cv2.cvtColor(band, cv2.COLOR_BGR2HSV))
    mask = ((hue > COUNTER_HUE[0]) & (hue < COUNTER_HUE[1])
            & (saturation > COUNTER_SATURATION) & (value > COUNTER_VALUE)).astype(np.uint8)
    count, _, stats, centres = cv2.connectedComponentsWithStats(mask, 8)
    left, top = ENEMY_BAND[0], ENEMY_BAND[1]
    found = []
    for index in range(1, count):
        _, _, box_width, box_height, area = stats[index]
        if area < COUNTER_MIN_AREA:
            continue
        squareness = box_width / max(box_height, 1)
        if not COUNTER_SQUARENESS[0] < squareness < COUNTER_SQUARENESS[1]:
            continue
        if not COUNTER_HEIGHT[0] <= box_height / height <= COUNTER_HEIGHT[1]:
            continue
        found.append((left + centres[index][0] / width, top + centres[index][1] / height))
    return sorted(found)


def weakness(task):
    """Say which attribute the enemies are weak to.

    Args:
        task: The running task.

    Returns:
        The attribute every enemy on screen shares, or None when they differ, when none was read, or when
        there is no frame to read.
    """
    half_x, half_y = BADGE_HALF
    seen = set()
    for centre_x, centre_y in enemy_counters(task):
        badge_x = centre_x + BADGE_OFFSET[0]
        badge_y = centre_y + BADGE_OFFSET[1]
        box = (badge_x - half_x, badge_y - half_y, badge_x + half_x, badge_y + half_y)
        attribute = attribute_of(patch_of(task, box))
        if attribute:
            seen.add(attribute)
    return seen.pop() if len(seen) == 1 else None
