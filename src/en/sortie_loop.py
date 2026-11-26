"""Start the next Sortie run from the lobby, so runs chain back to back on the Global client.

Upstream starts a run through its catch-all Enter, which the fork keeps on the round button at the right, so the lobby's centre Enter
was never pressed. Nothing picked the tier or set Lv.80's Risk Modifiers either, the Combatant List's random fallback could tap a stat
label instead of a name, and an empty Aether bar would have walked into the refill prompt.
"""

import difflib
import re

import numpy as np

from ok import Logger

from src.en import tested
from src.en.game_data import RISK_MODIFIERS, SORTIE_LEVELS
from src.en.handlers import insert_before, loaded, register, wrap
from src.en.navigation import ROSTER_NAME
from src.en.notify import announce
from src.en.overrides import RISK_PICKS, SORTIE_LEVEL
from src.en.quality import fold
from src.en.screen import centre_of, colour_share, frame_of, in_region, patch_of, text_in_region

logger = Logger.get_logger(__name__)

# What the catalog turns the client's "Enter" into.
ENTER = "进入"
# The lobby: the clears counter only it shows, at (0.111, 0.244), and its centre Enter at (0.499, 0.902). The formation's Enter is
# at x 0.723 and the Risk Modifiers page's at 0.930, so the band takes neither.
LOBBY_MARK = "Cumulative Sortie Clears"
LOBBY_MARK_BAND = (0.0, 0.18, 0.30, 0.30)
LOBBY_ENTER = (0.40, 0.85, 0.60, 0.95)
# The lobby's tier, "LV.80" over its numeral at (0.499, 0.457), and the arrows either side that step it. Lv.40 has no left arrow
# and Lv.80 no right one.
LEVEL_BAND = (0.42, 0.42, 0.58, 0.49)
LEVEL = re.compile(r"Lv\.?\s*(\d+)", re.IGNORECASE)
LOWER, HIGHER = (0.315, 0.50), (0.685, 0.50)
# Steps to allow before deciding the picked tier is locked. One more than the tiers, so a missed read gets a second look.
MAX_STEPS = len(SORTIE_LEVELS) + 1
LEVEL_STATE = "_en_sortie_level"
# The formation, as the catalog names it, with its Aether counter "16/320+" at (0.812, 0.047) and the run's cost "10" at (0.950, 0.914).
FORMATION = "主战员配置"
TITLE_BAND = (0.0, 0.0, 0.30, 0.09)
AETHER_BAND = (0.75, 0.0, 0.88, 0.09)
COST_BAND = (0.92, 0.88, 0.99, 0.95)
AETHER = re.compile(r"(\d+)\s*/\s*\d+")
COST = re.compile(r"^\s*(\d+)\s*$")
# The Risk Modifiers page: its title, the "Stage 3 /30" total at (0.761, 0.322), and the list left of the toggles.
RISK_TITLE = "Risk Modifiers"
STAGE_BAND = (0.55, 0.25, 0.99, 0.40)
STAGE = re.compile(r"Stage\s*(\d+)\s*/\s*\d+", re.IGNORECASE)
ROW_BAND = (0.0, 0.15, 0.47, 1.0)
# Each row's "+N Stages", which anchors it. OCR sometimes boxes it with the row's text, as "...through Heals +4 Stages".
ROW_COST = re.compile(r"\+\s*(\d+)\s*Stages?", re.IGNORECASE)
# Rows are pitched 0.15 apart and a wrapped line sits within 0.035 of its anchor, so half a row takes the whole row and nothing more.
ROW_REACH = 0.07
# How close a row's read has to be to a modifier's text. OCR drops a letter now and then, as in "nrices".
ROW_MATCH = 0.6
# The modifiers by their stage cost, each with its folded text, since a row is only ever matched against those of its own cost.
BY_COST = {}
for _name, _stages in RISK_MODIFIERS.items():
    BY_COST.setdefault(_stages, []).append((_name, fold(_name)))
# Each row's round toggle, sampled as a band either side of the row's y. On, 0.59 of it is orange, and off none of it is.
TOGGLE_X = 0.507
TOGGLE_LEFT, TOGGLE_RIGHT = 0.490, 0.524
TOGGLE_HALF = 0.03
ON_LOW, ON_HIGH = np.array((5, 150, 150)), np.array((25, 255, 255))
ON_SHARE = 0.3
# Where to scroll the list, and how far. Rows 6 to 8 sit below the first screen.
SCROLL_POINT = (0.25, 0.60)
SCROLL_AMOUNT = 3
MAX_SCROLLS = 6
# Attempts to reach the Stage the picks add up to before stopping rather than run with the wrong modifiers.
TRIES = 2
# Holds in `node_status` how far this run's Risk Modifiers have got. Upstream rebuilds `node_status` on every Enter, which clears it.
RISK_STATE = "_en_risk_modifiers"
# Names the roster filter in `wrap`'s record.
TAG = "real combatants only"

_patched = False


def number_in(task, pattern, region):
    """Read the first number a pattern finds in a region.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        pattern: A compiled pattern whose first group is the number.
        region: A `(left, top, right, bottom)` tuple in screen fractions.

    Returns:
        The number, or None when nothing in the region matches.
    """
    for box in task.all_texts or []:
        found = pattern.search(box.name)
        if found and in_region(box, region, task.width, task.height):
            return int(found.group(1))
    return None


def modifier_rows(boxes, width, height):
    """Read the Risk Modifiers rows on screen, each matched to the modifier it shows.

    Args:
        boxes: The OCR boxes of one pass.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        A list of `(modifier, y)` pairs, top to bottom, where `y` is the row's centre as a fraction. A row whose text matches no
        modifier of its cost is left out.
    """
    listed = [box for box in boxes if in_region(box, ROW_BAND, width, height)]
    rows = []
    for anchor in listed:
        cost = ROW_COST.search(anchor.name)
        if cost is None:
            continue
        _, y = centre_of(anchor, width, height)
        lines = sorted((box for box in listed if abs(centre_of(box, width, height)[1] - y) <= ROW_REACH), key=lambda box: box.y)
        text = fold(" ".join(ROW_COST.sub("", box.name) for box in lines))
        scored = [(difflib.SequenceMatcher(None, text, folded).ratio(), name) for name, folded in BY_COST.get(int(cost.group(1)), ())]
        score, name = max(scored, default=(0.0, None))
        if score >= ROW_MATCH:
            rows.append((name, y))
        else:
            logger.debug(f"Risk Modifiers row {text!r} at y {y:.3f} matches no +{cost.group(1)} modifier")
    return sorted(rows, key=lambda row: row[1])


def toggle_on(frame, y):
    """Read whether a row's toggle is on.

    Args:
        frame: The frame to read, or None when there is none.
        y: The row's centre, as a fraction of the screen height.

    Returns:
        True when on, False when off, and None when the toggle is off the frame.
    """
    patch = patch_of(frame, (TOGGLE_LEFT, y - TOGGLE_HALF, TOGGLE_RIGHT, y + TOGGLE_HALF))
    if patch is None:
        return None
    return colour_share(patch, ON_LOW, ON_HIGH) >= ON_SHARE


def step_toward_level(task, utils):
    """Tap the lobby's arrow one tier toward the picked Sortie Level, or stop the task when it cannot be reached.

    Args:
        task: The running task, on the Sortie lobby.
        utils: Upstream's `utils` module, for its config read and tap.

    Returns:
        True when it tapped or stopped, False once the lobby is on the picked tier or none is picked.
    """
    wanted = LEVEL.search(str(utils._get_config_value(task, SORTIE_LEVEL, "")))
    status = getattr(task, "node_status", None)
    if wanted is None or status is None:
        return False
    target = int(wanted.group(1))
    level = number_in(task, LEVEL, LEVEL_BAND)
    if level == target:
        return False
    steps = status.get(LEVEL_STATE, 0)
    if steps >= MAX_STEPS:
        announce(task, f"Sortie Level Lv.{target} could not be reached from Lv.{level}, so Sortie stops")
        task.disable()
        return True
    status[LEVEL_STATE] = steps + 1
    if level is not None:
        task.log_info(f"Sortie lobby on Lv.{level}, stepping toward Lv.{target}")
        utils._move_and_click(task, *(HIGHER if level < target else LOWER))
    task.sleep(1)
    return True


def lobby_handler(utils):
    """Build the handler that sets the Sortie lobby to the picked tier and presses its Enter.

    Args:
        utils: Upstream's `utils` module, for the run reset its own Enter press makes.

    Returns:
        The handler.
    """
    def handle_sortie_lobby(task):
        if text_in_region(task, LOBBY_MARK, LOBBY_MARK_BAND) is None:
            return False
        button = text_in_region(task, ENTER, LOBBY_ENTER)
        if button is None:
            return False
        if step_toward_level(task, utils):
            return True
        task.log_info("on the Sortie lobby, pressing Enter for the next run")
        task.click_box(button)
        utils.reset_mission_status(task)
        task.sleep(1)
        return True

    return handle_sortie_lobby


def handle_out_of_aether(task):
    """Stop the task on the formation when the Aether left cannot pay for a run.

    Args:
        task: The running task.

    Returns:
        True when it stopped the task.
    """
    if text_in_region(task, FORMATION, TITLE_BAND) is None:
        return False
    aether = number_in(task, AETHER, AETHER_BAND)
    cost = number_in(task, COST, COST_BAND)
    if aether is None or cost is None or aether >= cost:
        return False
    announce(task, f"Out of Aether ({aether} left, a run costs {cost}), so Sortie stops")
    task.disable()
    return True


def risk_handler(utils):
    """Build the handler that sets Lv.80's Risk Modifiers to the picks before the run is entered.

    One tap or scroll per frame, so every decision reads a frame drawn after the last one. Once every row has been seen right and
    the Stage matches the picks, it steps aside and the Enter handler starts the run.

    Args:
        utils: Upstream's `utils` module, for its config read, tap and scroll.

    Returns:
        The handler.
    """
    order = list(RISK_MODIFIERS)

    def handle_risk_modifiers(task):
        status = getattr(task, "node_status", None)
        if status is None or text_in_region(task, RISK_TITLE, TITLE_BAND) is None:
            return False
        stage = number_in(task, STAGE, STAGE_BAND)
        if stage is None:
            return False
        state = status.setdefault(RISK_STATE, {"checked": set(), "scrolls": 0, "tries": 0, "done": False})
        if state["done"]:
            return False
        wanted = {name for name in utils._get_config_value(task, RISK_PICKS, []) if name in RISK_MODIFIERS}
        frame = frame_of(task)
        rows = modifier_rows(task.all_texts or [], task.width, task.height)
        for name, y in rows:
            on = toggle_on(frame, y)
            if on is None:
                continue
            if on != (name in wanted):
                task.log_info(f"Risk Modifiers: turning {'off' if on else 'on'} {name}")
                utils._move_and_click(task, TOGGLE_X, y)
                task.sleep(1)
                return True
            state["checked"].add(name)

        missing = [name for name in order if name not in state["checked"]]
        if missing and state["scrolls"] < MAX_SCROLLS:
            state["scrolls"] += 1
            # Toward the first row not yet seen. The list keeps its scroll, so it can open part way down.
            down = not rows or order.index(missing[0]) > order.index(rows[0][0])
            utils._scroll_card_page(task, *SCROLL_POINT, -SCROLL_AMOUNT if down else SCROLL_AMOUNT, "Risk Modifiers")
            task.sleep(1)
            return True

        goal = sum(RISK_MODIFIERS[name] for name in wanted)
        if stage == goal:
            state["done"] = True
            unseen = f", never read {missing}" if missing else ""
            task.log_info(f"Risk Modifiers set to Stage {stage}: {sorted(wanted) or 'none'}{unseen}")
            return False
        state["tries"] += 1
        if state["tries"] >= TRIES:
            announce(task, f"Risk Modifiers read Stage {stage}, not the {goal} the picks add up to, so Sortie stops")
            task.disable()
            return True
        task.log_info(f"Risk Modifiers read Stage {stage}, not {goal}, so reading every row again")
        state["checked"].clear()
        state["scrolls"] = 0
        return True

    return handle_risk_modifiers


def roster_only(original):
    """Keep the Combatant List's picks on real combatants, the least played first while Draft Least Played is on.

    Args:
        original: Upstream's `_battle_member_boxes`.

    Returns:
        The `_battle_member_boxes` to run in its place.
    """
    def _battle_member_boxes(task):
        return least_played([box for box in original(task) if ROSTER_NAME.search(box.name)])

    return _battle_member_boxes


def least_played(boxes):
    """Narrow the Combatant List's names to those who have played least, while Draft Least Played is on.

    Args:
        boxes: The OCR boxes holding a roster name.

    Returns:
        The boxes to pick from, all of them while Draft Least Played is off.
    """
    counts = tested.plays()
    if counts is None or not boxes:
        return boxes
    plays = [counts[ROSTER_NAME.search(box.name).group(0)] for box in boxes]
    return [box for box, played in zip(boxes, plays) if played == min(plays)]


def install():
    """Add the run-chaining handlers to Sortie and narrow its Combatant List to real names."""
    utils = loaded("utils")
    utils_sortie = loaded("utils_sortie")
    if utils is None or utils_sortie is None:
        return
    wrap(utils_sortie, "_battle_member_boxes", roster_only, TAG)
    insert_before("handle_enter", lobby_handler(utils), only=("utils_sortie",))
    insert_before("handle_enter", risk_handler(utils), only=("utils_sortie",))
    insert_before("handle_battle_member_config", handle_out_of_aether, only=("utils_sortie",))


def apply():
    """Chain Sortie runs from the lobby."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
