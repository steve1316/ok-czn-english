"""Start the next Sortie run from the lobby, so runs chain back to back on the Global client.

Upstream starts a run through its catch-all Enter, which the fork keeps on the round button at the right, so the lobby's centre Enter is
missed. Upstream also sets no tier, Hardcore Mode or Risk Modifiers, and its Combatant List pick can land on a stat label.
"""

import difflib
import re

import numpy as np

from ok import Logger

from src.en import tested
from src.en.game_data import COMBATANTS, RISK_MODIFIERS, SORTIE_LEVELS
from src.en.enter import ENTER
from src.en.handlers import insert_before, loaded, register, wrap
from src.en.navigation import ROSTER_NAME
from src.en.notify import announce
from src.en.overrides import AUTO_DRAFT, DRAFTED_COMBATANT, HARDCORE, RISK_PICKS, SORTIE_LEVEL
from src.en.quality import fold
from src.en.screen import centre_of, colour_share, frame_of, in_region, patch_of, text_in_region, white_mask

logger = Logger.get_logger(__name__)

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
# The button a cleared boss leaves at (0.906, 0.916), text id `assault_skip_ingame_marking_button`, which starts the run's ending story.
# Nothing in `ok_tasks/` reads it, so it is matched in English.
SEND_COORDINATES = "Send Coordinates"
SEND_BAND = (0.78, 0.85, 1.0, 0.98)
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
# The Combatant List's names, between its title and its Details and Assign buttons, as upstream reads them. It scrolls as far as upstream does.
LIST_BAND = (0.100, 0.100, 0.984, 0.892)
LIST_SCROLLS = 5
# The formation's Hardcore Mode switch, a track at x 0.64-0.70, and the end its white knob slides to when on. Measured 2026-11-26, 0.88
# of that end is white while on and none of it while off. A share between is the knob mid-slide.
HARDCORE_SWITCH = (0.665, 0.047)
KNOB_END = (0.672, 0.030, 0.692, 0.065)
KNOB_ON, KNOB_OFF = 0.5, 0.1
# The notice switching it on opens, titled "Hardcore Mode", and its close button.
HARDCORE_TITLE = "Hardcore Mode"
HARDCORE_CLOSE = (0.97, 0.055)
# The switch's animation runs 2 seconds before the knob settles at its new end, so the next read waits it out.
HARDCORE_SETTLE = 2.5
# Taps on the switch per run before deciding it will not flip. Kept in `node_status`, so cleared once per run.
HARDCORE_TAPS = 3
HARDCORE_STATE = "_en_hardcore_taps"
# The formation's lead card, x 0.04-0.21, which reopens the Combatant List when tapped, and its role label ("Attack" at (0.178, 0.799)),
# drawn only once a combatant fills the slot. Upstream opens the list itself for an empty slot.
SLOT_CARD = (0.12, 0.45)
SLOT_ROLE_BAND = (0.12, 0.77, 0.24, 0.83)
# Set in `node_status` once this run's filled slot has been checked against the pick, so the list is reopened once per run.
SLOT_CHECKED = "_en_slot_checked"
# How long the Combatant List takes to close after Back. It is still drawn 0.6s after the press, and a tap on it then cancels the Back.
LIST_CLOSE = 2
# Name the roster filter, the Drafted pick and the wait after Back in `wrap`'s record.
TAG = "real combatants only"
DRAFT_TAG = "Drafted Combatant pick"
CLOSE_TAG = "waits out the list closing"

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


def stop(task, message):
    """Tell the user why Sortie stops, and stop it.

    Args:
        task: The running Sortie task.
        message: What the notice says.

    Returns:
        True, so the handler claims the frame.
    """
    announce(task, message)
    task.disable()
    return True


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
        return stop(task, f"Sortie Level Lv.{target} could not be reached from Lv.{level}, so Sortie stops")
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


def handle_send_coordinates(task):
    """Press Send Coordinates after the boss that ends a run, which the battle reader otherwise holds as a battle with an empty hand.

    Args:
        task: The running task.

    Returns:
        True when the button was pressed.
    """
    button = text_in_region(task, SEND_COORDINATES, SEND_BAND)
    if button is None:
        return False
    task.log_info("the boss is down, pressing Send Coordinates to end the run")
    task.click_box(button)
    task.sleep(1)
    return True


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
    return stop(task, f"Out of Aether ({aether} left, a run costs {cost}), so Sortie stops")


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
            return stop(task, f"Risk Modifiers read Stage {stage}, not the {goal} the picks add up to, so Sortie stops")
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


def listed(task, name):
    """Find a combatant's name on the Combatant List.

    Args:
        task: The running task, whose `all_texts` holds the list's OCR pass.
        name: The combatant to look for, as the roster spells it.

    Returns:
        The box holding the name, or None when it is not on screen.
    """
    return next((box for box in task.all_texts or [] if in_region(box, LIST_BAND, task.width, task.height) and name in ROSTER_NAME.findall(box.name)), None)


def drafted_pick(utils, utils_sortie):
    """Build the wrapper that assigns the Drafted Combatant setting's pick from the Combatant List.

    Args:
        utils: Upstream's `utils` module, for its config read and OCR clean-up.
        utils_sortie: Upstream's `utils_sortie` module, for its Assign press.

    Returns:
        A factory for `wrap`, taking upstream's `_select_battle_member`.
    """
    def factory(original):
        def _select_battle_member(task, max_scrolls=LIST_SCROLLS):
            pick = utils._get_config_value(task, DRAFTED_COMBATANT, AUTO_DRAFT)
            if pick not in COMBATANTS:
                # Draft Least Played spreads debug runs over the roster, so it keeps upstream's pick from the least played.
                if tested.plays() is not None:
                    return original(task, max_scrolls)
                task.log_info("Drafted Combatant is Auto, assigning the game's own pick")
                return utils_sortie._confirm_battle_member_selection(task)
            for scroll in range(max_scrolls + 1):
                box = listed(task, pick)
                if box is not None:
                    task.log_info(f"Drafted Combatant {pick} found on the Combatant List, assigning")
                    task.click_box(box)
                    task.sleep(0.5)
                    return utils_sortie._confirm_battle_member_selection(task)
                if scroll < max_scrolls:
                    task.move_relative(0.5, 0.5)
                    task.scroll_relative(0.5, 0.7, -3)
                    task.sleep(0.5)
                    task.all_texts = utils._simplify_texts(task.ocr())
            # The game's own pick stays selected through the scrolling, so Assign still fills the slot.
            task.log_info(f"Drafted Combatant {pick} is not on the Combatant List, assigning the game's own pick")
            return utils_sortie._confirm_battle_member_selection(task)

        return _select_battle_member

    return factory


def closing_list(original):
    """Wrap upstream's `_confirm_battle_member_selection` so the list has closed before the next frame is read.

    Upstream waits after Assign but not after Back.

    Args:
        original: Upstream's `_confirm_battle_member_selection`, or another patch's wrapper of it.

    Returns:
        The wrapped function.
    """
    def _confirm_battle_member_selection(task):
        result = original(task)
        task.sleep(LIST_CLOSE)
        return result

    return _confirm_battle_member_selection


def slot_check_handler(utils):
    """Build the handler that reopens the Combatant List once per run when a filled slot may not hold the Drafted Combatant pick.

    On the list, the pick is tapped and assigned. When it already fills the slot, Assign stays grey and upstream presses Back instead.

    Args:
        utils: Upstream's `utils` module, for its config read and tap.

    Returns:
        The handler.
    """
    def handle_slot_check(task):
        status = getattr(task, "node_status", None)
        if status is None or status.get(SLOT_CHECKED) or text_in_region(task, FORMATION, TITLE_BAND) is None:
            return False
        if utils._get_config_value(task, DRAFTED_COMBATANT, AUTO_DRAFT) not in COMBATANTS:
            return False
        if not any(box.name.strip() and in_region(box, SLOT_ROLE_BAND, task.width, task.height) for box in task.all_texts or []):
            return False
        status[SLOT_CHECKED] = True
        task.log_info("opening the Combatant List to check the formation holds the Drafted Combatant pick")
        utils._move_and_click(task, *SLOT_CARD)
        task.sleep(2)
        return True

    return handle_slot_check


def hardcore_on(frame):
    """Read whether the formation's Hardcore Mode switch is on, from how white the end of its track is.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        True when on, False when off, and None mid-slide or with no frame.
    """
    patch = patch_of(frame, KNOB_END)
    if patch is None or patch.size == 0:
        return None
    white = white_mask(patch)
    share = np.count_nonzero(white) / white.size
    if share >= KNOB_ON:
        return True
    if share <= KNOB_OFF:
        return False
    return None


def hardcore_handler(utils):
    """Build the handler that flips the formation's Hardcore Mode switch to the setting, and closes the notice it opens.

    Args:
        utils: Upstream's `utils` module, for its config read and tap.

    Returns:
        The handler.
    """
    def handle_hardcore_mode(task):
        if text_in_region(task, HARDCORE_TITLE, TITLE_BAND) is not None:
            task.log_info("closing the Hardcore Mode notice")
            utils._move_and_click(task, *HARDCORE_CLOSE)
            task.sleep(1)
            return True
        status = getattr(task, "node_status", None)
        if status is None or text_in_region(task, FORMATION, TITLE_BAND) is None:
            return False
        wanted = bool(utils._get_config_value(task, HARDCORE, False))
        on = hardcore_on(frame_of(task))
        if on is None:
            logger.debug("Hardcore Mode switch unread, mid-slide or no frame")
            return False
        if on == wanted:
            return False
        taps = status.get(HARDCORE_STATE, 0)
        if taps >= HARDCORE_TAPS:
            return stop(task, f"Hardcore Mode stayed {'on' if on else 'off'} after {taps} taps, so Sortie stops")
        status[HARDCORE_STATE] = taps + 1
        task.log_info(f"Hardcore Mode is {'on' if on else 'off'}, switching it {'on' if wanted else 'off'}")
        utils._move_and_click(task, *HARDCORE_SWITCH)
        task.sleep(HARDCORE_SETTLE)
        return True

    return handle_hardcore_mode


def install():
    """Add the run-chaining handlers to Sortie and have its Combatant List assign the Drafted Combatant pick."""
    utils = loaded("utils")
    utils_sortie = loaded("utils_sortie")
    if utils is None or utils_sortie is None:
        return
    wrap(utils_sortie, "_battle_member_boxes", roster_only, TAG)
    wrap(utils_sortie, "_select_battle_member", drafted_pick(utils, utils_sortie), DRAFT_TAG)
    wrap(utils_sortie, "_confirm_battle_member_selection", closing_list, CLOSE_TAG)
    insert_before("handle_expedition_result", handle_send_coordinates, only=("utils_sortie",))
    insert_before("handle_enter", lobby_handler(utils), only=("utils_sortie",))
    insert_before("handle_enter", risk_handler(utils), only=("utils_sortie",))
    insert_before("handle_battle_member_config", handle_out_of_aether, only=("utils_sortie",))
    insert_before("handle_battle_member_config", slot_check_handler(utils), only=("utils_sortie",))
    insert_before("handle_battle_member_config", hardcore_handler(utils), only=("utils_sortie",))


def apply():
    """Chain Sortie runs from the lobby."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
