"""Read what the battle screen says about the moment a card is being chosen in.

`SortieMode.run` pays for one full-frame OCR a second and every handler reads the result for free, so
everything here comes out of that pass or out of raw pixels. Nothing in this module runs OCR.
"""

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from ok import Logger

from src.en.game_battle import ATTRIBUTES
from src.en.screen import frame_of, hsv_of, patch_of, white_mask

logger = Logger.get_logger(__name__)

# The Action Point readout, as a relative box. Read from colour because OCR returns no box for the digit at
# all - not in a full frame and not on a tight upscaled crop, both checked. The game draws it bright blue with
# a glow while there are points to spend and a thin grey outline once there are none. Deliberately tight on
# the digit: the hand counter below it and the decorative line through its middle both sit outside, so neither
# can be counted as a lit reading.
ACTION_POINTS = (0.488, 0.898, 0.528, 0.948)
# How bright a pixel has to be to count as part of the digit rather than the scene behind it. 200 rather than
# the obvious 170 because one frame's background sits at exactly 170 across a large flat area, which would
# have read an empty turn as a full one.
LIT = 200
# The share of the readout that has to be lit before it is read as "points remain". Across 30 real frames, 25
# empty and 5 with points, the lit share came out at most 0.031 empty and at least 0.130 full - four times
# over - and it holds from 1280x720 to 2560x1440. `tests/TestBoard.py` pins the tightest pair, so anything
# narrowing the gap fails there first.
LIT_ENOUGH = 0.08

# The three Ego slots, in the order the panel shows them.
EGO_KEYS = ("F1", "F2", "F3")
# Where each slot's cost badge sits. The three are evenly spaced down the panel, and the figures come from the
# OCR pass, which does read the bottom slot's badge and both of the outer labels even though it misses the
# Action Point digit entirely.
EGO_BADGE_X = 0.065
EGO_BADGE_Y = {"F1": 0.7140, "F2": 0.8050, "F3": 0.8960}
EGO_BADGE_HALF = (0.0090, 0.0150)
# The game tints an affordable badge, pale blue or the yellow-green of a reduced cost, and draws one it cannot pay for in grey.
BADGE_LIT = 120
TINT_SATURATION = 30
# How much of a badge's lit pixels have to be tinted before the Ego behind it is treated as one that can be fired. Measured: 1.0 on a
# blue badge, 0.995 on a reduced one and under 0.01 on a grey one.
EGO_READY = 0.5
# The EP bar left of the Ego panel: seven segments down from the top, lit pale blue for each point banked and pale yellow for the
# points a previewed Ego would spend. Upstream's full-bar pixel at 0.947 is the seventh. A segment still filling is lit to about 203.
EP_SEGMENT_X = (0.020, 0.044)
EP_SEGMENT_TOP = 0.7806
EP_SEGMENT_PITCH = 0.0278
EP_SEGMENT_HALF = 0.0050
EP_MAX = 7
EP_LIT = 230
EP_LIT_ENOUGH = 0.6

# The team HP bar along the top, row 36 to 46 at 1080p. Its green stops where the enemy's next hit would leave the team, and the
# stretch from there to the HP the readout states flashes red. The readout's digits are drawn over the middle of the bar, so a
# column counts as green when `GREEN_ROWS` of its rows are.
TEAM_BAR = (0.0234, 0.0333, 0.4000, 0.0426)
GREEN_HUE = (40, 85)
GREEN_SATURATION = 100
GREEN_VALUE = 120
GREEN_ROWS = 2

# The Absolute Invincibility badge drawn among an enemy's statuses, cut from a 1080p frame and matched on its white strokes.
INVULNERABLE_IMAGE = Path(__file__).with_name("images") / "absolute_invincibility.png"
TEMPLATE_HEIGHT = 1080
# It scores 1.0 on the capture it was cut from and at most 0.49 on 846 others.
INVULNERABLE_MATCH = 0.7

# Where the enemies' counters and badges are drawn: below the top HUD, above the cards and the combatants.
ENEMY_BAND = (0.30, 0.12, 1.00, 0.60)
# The action counter's own magenta, and the shape it is drawn in. The HP bar beside it is a lighter pink and
# is far too wide to pass the squareness test, so neither can be mistaken for the other.
# `tests/images/enemy_instinct.png` pins the counter and the badge beside it against the game's own rendering.
COUNTER_HUE = (160, 178)
COUNTER_SATURATION = 170
COUNTER_VALUE = 120
COUNTER_MIN_AREA = 400
COUNTER_SQUARENESS = (0.6, 1.7)
# How tall a counter is, as a share of the frame. Every real one measures between 0.057 and 0.060, while
# the magenta flashes an attack throws up run from 0.08 to 0.38 and the smaller markers sit at 0.033, so
# this band is what keeps a hit landing on screen from being counted as another enemy. `attack_flash.png`
# holds the burst that passes every other test and fails here.
COUNTER_HEIGHT = (0.045, 0.072)
# Where the weakness badge sits relative to its counter, and how much of it to sample.
WEAKNESS_OFFSET = (0.0185, 0.0225)
WEAKNESS_HALF = (0.0085, 0.0085)
WEAKNESS_SATURATION = 150
WEAKNESS_VALUE = 130
# How much of the sampled patch has to be strongly coloured before it is read as a badge rather than scenery.
WEAKNESS_ENOUGH = 0.20
# The hue the client draws each of its attribute colours in. The client stores attributes as colours, so
# `ATTRIBUTES` already says which is which. Measured at 15, 78 and 133 out of 180 with a spread of about three
# each, and only the orange one has been confirmed against the game, as Instinct. Red sits at 0 rather than
# 180 only because that is the same place on a hue wheel, and the nearest of these five decides which
# attribute a badge is.
ATTRIBUTE_HUES = {"RED": 0, "ORANGE": 15, "GREEN": 78, "BLUE": 110, "PURPLE": 133}
# How far a badge's hue may sit from the nearest of those before it is treated as not a badge at all.
HUE_TOLERANCE = 20


def box_around(centre_x, centre_y, half):
    """Build a relative box of a given size around a point.

    Args:
        centre_x: Where the middle of the box sits across the frame, as a fraction.
        centre_y: Where the middle of the box sits down the frame, as a fraction.
        half: The `(x, y)` half-size, in the same fractions.

    Returns:
        A `(left, top, right, bottom)` tuple.
    """
    half_x, half_y = half
    return (centre_x - half_x, centre_y - half_y, centre_x + half_x, centre_y + half_y)


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
        True while the readout is lit - whether any points remain, not how many, which is all the planner
        needs and all the screen gives away. Also True when there is no frame to read, because ending a turn
        that had not finished costs more than trying a card that will not play.
    """
    patch = patch_of(frame_of(task), ACTION_POINTS)
    if patch is None:
        return True
    return lit_fraction(patch) >= LIT_ENOUGH


def tinted_fraction(patch):
    """Say how much of a lit patch is drawn in colour rather than grey.

    Measured against the lit pixels rather than the whole patch, so a badge sitting on a dark background and
    one sitting on a bright scene are judged the same way.

    Args:
        patch: The pixels to measure, in BGR.

    Returns:
        The tinted share of the lit pixels, from 0 to 1, and 0 for an empty patch.
    """
    hsv = hsv_of(patch)
    if hsv is None:
        return 0.0
    _, saturation, value = cv2.split(hsv)
    lit = value > BADGE_LIT
    return float(np.count_nonzero(lit & (saturation > TINT_SATURATION))) / max(int(np.count_nonzero(lit)), 1)


def affordable_egos(task):
    """List the Ego skills the EP bar can currently pay for.

    Args:
        task: The running task.

    Returns:
        The keys that fire an affordable Ego, in panel order. Empty when none can be paid for, and empty when
        there is no frame to read, since firing one blind is the behaviour this exists to replace.
    """
    frame = frame_of(task)
    ready = []
    for key in EGO_KEYS:
        box = box_around(EGO_BADGE_X, EGO_BADGE_Y[key], EGO_BADGE_HALF)
        if tinted_fraction(patch_of(frame, box)) > EGO_READY:
            ready.append(key)
    return ready


def banked_points(frame):
    """Count the EP the bar has banked.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        How many segments are lit from the top, 0 to `EP_MAX`, and 0 when there is no frame.
    """
    banked = 0
    for index in range(EP_MAX):
        middle = EP_SEGMENT_TOP + index * EP_SEGMENT_PITCH
        patch = patch_of(frame, (EP_SEGMENT_X[0], middle - EP_SEGMENT_HALF, EP_SEGMENT_X[1], middle + EP_SEGMENT_HALF))
        if patch is None or patch.size == 0 or np.count_nonzero(patch.max(axis=2) > EP_LIT) < EP_LIT_ENOUGH * patch.shape[0] * patch.shape[1]:
            break
        banked += 1
    return banked


def team_after_hit(frame):
    """Say how much of the team's HP will be left once the enemy's next hit lands.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        The share of the team's maximum HP the bar's green reaches, or None when no green is on the bar or there is no frame.
    """
    hsv = hsv_of(patch_of(frame, TEAM_BAR))
    if hsv is None:
        return None
    hue, saturation, value = cv2.split(hsv)
    green = (hue > GREEN_HUE[0]) & (hue < GREEN_HUE[1]) & (saturation > GREEN_SATURATION) & (value > GREEN_VALUE)
    columns = np.flatnonzero(np.count_nonzero(green, axis=0) >= GREEN_ROWS)
    if not columns.size:
        return None
    return float(columns[-1] + 1) / green.shape[1]


@lru_cache(maxsize=4)
def invulnerable_template(height):
    """Load the Absolute Invincibility badge, scaled to a frame's size.

    Args:
        height: The frame height in pixels.

    Returns:
        The badge's white mask, or None when the image cannot be read.
    """
    image = cv2.imread(str(INVULNERABLE_IMAGE))
    if image is None:
        logger.warning(f"could not read the invulnerability badge from {INVULNERABLE_IMAGE}")
        return None
    scale = height / TEMPLATE_HEIGHT
    if scale != 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return white_mask(image)


def enemy_invulnerable(frame):
    """Say whether an enemy is showing Absolute Invincibility, which stops it losing Health for the turn.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        True when the badge is among the enemy statuses. False when it is not, or there is no frame.
    """
    patch = patch_of(frame, ENEMY_BAND)
    if patch is None or patch.size == 0:
        return False
    template = invulnerable_template(frame.shape[0])
    if template is None or patch.shape[0] < template.shape[0] or patch.shape[1] < template.shape[1]:
        return False
    return float(cv2.matchTemplate(white_mask(patch), template, cv2.TM_CCOEFF_NORMED).max()) >= INVULNERABLE_MATCH


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

    Assumes a battle screen, the only place this is reached from: swept over `captures/`, the 22 battle frames
    read Instinct or nothing, but red artwork elsewhere - a Card Epiphany screen, a full-screen portrait -
    throws up shapes that pass for counters and reads as Passion.

    Args:
        patch: The pixels the badge was sampled from, in BGR.

    Returns:
        The attribute's name, or None when the patch holds no badge worth reading.
    """
    hsv = hsv_of(patch)
    if hsv is None:
        return None
    hue, saturation, value = cv2.split(hsv)
    strong = (saturation > WEAKNESS_SATURATION) & (value > WEAKNESS_VALUE)
    if np.count_nonzero(strong) < WEAKNESS_ENOUGH * strong.size:
        return None
    middle = int(np.median(hue[strong]))
    # The counter sitting beside the badge is magenta, which is red's neighbour on the hue wheel, so its own
    # colour would otherwise read as a confident Passion. Anything in that band is the counter, or one of the
    # effects the game draws in the same colour, rather than a badge.
    if COUNTER_HUE[0] < middle < COUNTER_HUE[1]:
        return None
    colour = min(ATTRIBUTE_HUES, key=lambda name: hue_distance(middle, ATTRIBUTE_HUES[name]))
    if hue_distance(middle, ATTRIBUTE_HUES[colour]) > HUE_TOLERANCE:
        return None
    return ATTRIBUTES.get(colour)


def enemy_counters(frame):
    """Find the action counter of every enemy on screen.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        A list of `(x, y)` centres in fractions of the frame, left to right.
    """
    hsv = hsv_of(patch_of(frame, ENEMY_BAND))
    if hsv is None:
        return []
    height, width = frame.shape[:2]
    # One pass over the three channels rather than three. The bounds `inRange` takes are inclusive and the
    # ones named above are exclusive, hence the step in at each end.
    mask = cv2.inRange(hsv, (COUNTER_HUE[0] + 1, COUNTER_SATURATION + 1, COUNTER_VALUE + 1),
                       (COUNTER_HUE[1] - 1, 255, 255))
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

    No preference when they disagree, because no capture yet shows a mixed fight to check a majority against.

    Args:
        task: The running task.

    Returns:
        The attribute every enemy on screen shares, or None when they differ, when none was read, or when
        there is no frame to read.
    """
    frame = frame_of(task)
    seen = set()
    for centre_x, centre_y in enemy_counters(frame):
        badge = box_around(centre_x + WEAKNESS_OFFSET[0], centre_y + WEAKNESS_OFFSET[1], WEAKNESS_HALF)
        attribute = attribute_of(patch_of(frame, badge))
        if attribute:
            seen.add(attribute)
    return seen.pop() if len(seen) == 1 else None
