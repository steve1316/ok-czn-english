"""Take Sortie to the Combatants screen once a run, and skip the trip when a run already starts there.

Capturing the target combatant's portrait takes two handlers, and both tap their way to a page that may already
be open. `handle_save_target_member` taps the menu icon and waits two seconds, guarded only by a "have I done
this yet" flag, and `handle_archive_target_member` then taps the 3-person icon and the Combatants tab before
reading anything, which on a run started there shuts the page and reopens it. Sortie never makes the trip at all.
"""

import contextlib
import dataclasses
import re

from ok import Logger

from src.en.battle import PARTY
from src.en.handlers import insert_before, loaded, register, replace, standing_in, wrap
from src.en.game_data import COMBATANTS
from src.en.screen import combatant_names

logger = Logger.get_logger(__name__)

# Where the information page draws its member tab icon. Same region `handle_archive_target_member` searches,
# so agreeing with it is the point - if it can find the page, we must not be navigating towards it.
MEMBER_INFO_REGION = (0.005, 0.018, 0.080, 0.343)
MEMBER_INFO_FEATURES = ["memberinfo", "memberinfo2"]

# Where upstream taps to select the Combatants tab, read off the capture. Check this if a rebase moves it.
# The 3-person icon already lands on this tab, so the tap is dropped on every read.
COMBATANTS_TAB = (0.201, 0.056)
# Any combatant on the roster, as a whole word, so a read with a level stuck on still counts and a short name
# like "Nia" cannot match inside a longer one. The sibling tabs list Partners, who are not on this roster.
ROSTER_NAME = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in COMBATANTS) + r")\b")
# Where the map draws the team's portraits. Tapping one opens the information page - the tap Chaos makes in `handle_save_target_member`.
TEAM_PORTRAITS = (0.182, 0.081)
# Counts in `node_status` the taps Sortie has made towards the team, so a page that never opens costs a few tries rather than every frame.
# Upstream rebuilds `node_status` when a run or a layer starts, which is what clears it.
TEAM_TAPPED = "_en_team_tapped"
TEAM_TRIES = 3
# The two marks `handle_route_selection` knows the route map by. Check these if a rebase moves them.
ROUTE_POSITION = (0.335, 0.568, 0.453, 0.751)
ROUTE_NOTICE = (0.186, 0.850)
ROUTE_NOTICE_TEXT = "无法接收到梦境号"
# The handler Sortie's trip runs ahead of, the same place Chaos lists its own.
SORTIE_ANCHOR = "handle_route_selection"

_patched = False


@dataclasses.dataclass
class Dropped:
    """Counts the taps the stand-ins swallowed, so a capture that has changed shape gets noticed."""

    tab: int = 0   # taps on the Combatants tab that were dropped; upstream makes exactly one
    icon: int = 0  # box clicks that were dropped, all of them the 3-person icon; upstream makes exactly one
    # Dropping the two recovers about 1.6s, most of it `click_box`'s own `after_sleep`.


def on_member_info_page(task):
    """Report whether the information page is already open.

    Args:
        task: The running task.

    Returns:
        True when the page's own icon is on screen.
    """
    try:
        found = task.find_one(
            feature_name=MEMBER_INFO_FEATURES,
            box=task.box_of_screen(*MEMBER_INFO_REGION),
        )
    except Exception as error:
        # A capture that has not settled yet must not stop the run; fall through to upstream's navigation.
        logger.warning(f"could not look for the information page, navigating as usual: {error}")
        return False
    return bool(found)


def on_combatants_tab(task):
    """Report whether the Combatants tab is already open.

    The information page opens on this tab, so this is the normal case. A name off the combatant roster in one
    of the three slots proves it, whoever the run is farming - including nobody.

    Args:
        task: The running task.

    Returns:
        True when a combatant is named in one of the three slots.
    """
    utils = loaded("utils")
    if utils is None:
        return False
    return any(ROSTER_NAME.search(name) for name in combatant_names(task, utils))


def without_the_tab_tap(original, dropped):
    """Build a `_move_and_click` that drops the tap selecting the Combatants tab.

    Args:
        original: The real `_move_and_click`, which every other tap still goes through.
        dropped: The tally to record the skipped tap on.

    Returns:
        The replacement.
    """
    # Named for the handler it stands in for on purpose: `_move_and_click` logs the name of the frame that
    # called it, and a tap that does go through should still show up in the log as upstream's own capture.
    def handle_archive_target_member(task, x, y):
        if (x, y) == COMBATANTS_TAB:
            dropped.tab += 1
            return None
        return original(task, x, y)

    return handle_archive_target_member


def without_the_icon_tap(dropped):
    """Build a `click_box` that drops the tap on the 3-person icon.

    Upstream's capture clicks exactly one box, the icon that reopens the page it is already looking at, so
    dropping every box click for the length of the call drops that one and nothing else. The tally is what
    keeps that assumption honest if upstream ever grows a second one.

    Args:
        dropped: The tally to record the skipped tap on.

    Returns:
        The replacement `click_box`.
    """
    def click_box(box, *args, **kwargs):
        dropped.icon += 1
        return None

    return click_box


def reading_in_place(original):
    """Wrap the capture so it reads the tab it is already looking at.

    Args:
        original: Upstream's `handle_archive_target_member`.

    Returns:
        The wrapped handler.
    """
    def handle_archive_target_member(task):
        utils_chaos = loaded("utils_chaos")
        if utils_chaos is None:
            return original(task)
        in_place = on_combatants_tab(task)
        if in_place:
            logger.info("already on the Combatants tab, reading the three names without tapping back to it")
        dropped = Dropped()
        # Stood in for rather than reimplemented: everything the capture does after the two taps - the OCR,
        # the name match and the six portrait crops - is upstream's, and none of it changes.
        tab_tap = without_the_tab_tap(utils_chaos._move_and_click, dropped)
        icon_tap = standing_in(task, click_box=without_the_icon_tap(dropped)) if in_place else contextlib.nullcontext()
        with standing_in(utils_chaos, _move_and_click=tab_tap), icon_tap:
            handled = original(task)
        # Only a frame upstream handled has made its taps - on any other it declined before tapping anything.
        if handled and (dropped.tab, dropped.icon) != (1, int(in_place)):
            # Loud on purpose. Both taps are recognised by shape rather than by name, so upstream changing
            # either is invisible until someone reads the log - either a tap it still needed was swallowed,
            # or the skip quietly stopped saving anything.
            logger.warning(f"expected to drop one tab tap and {int(in_place)} icon tap, dropped {dropped.tab} and "
                           f"{dropped.icon}: upstream's capture has changed shape, so this skip needs a look")
        return handled

    return handle_archive_target_member


def on_route_map(task, utils):
    """Tell whether the route selection map is up, by the same marks `handle_route_selection` checks.

    Args:
        task: The running Sortie task, whose current frame is read.
        utils: Upstream's `utils` module, for its text lookup at a point.

    Returns:
        True on the route map.
    """
    notice = utils.find_box_at_point(task, *ROUTE_NOTICE)
    return bool(task.find_feature(feature_name="position", box=task.box_of_screen(*ROUTE_POSITION))
                or (notice and ROUTE_NOTICE_TEXT in notice.name))


def handle_open_team(task):
    """Open the information page from the route map as a Sortie run or layer starts, so the team is read before a battle.

    `handle_archive_target_member` then reads the names and closes the page, as it does for Chaos. Other screens show the portraits too, but a
    pending dialog there swallows the tap, so only the map is trusted. A tap that reads no team is retried, up to `TEAM_TRIES`.

    Args:
        task: The running Sortie task.

    Returns:
        True when the tap was made this frame.
    """
    utils = loaded("utils")
    tries = task.node_status.get(TEAM_TAPPED, 0)
    if utils is None or tries >= TEAM_TRIES or (tries and getattr(task, PARTY, None)) or not on_route_map(task, utils):
        return False
    task.node_status[TEAM_TAPPED] = tries + 1
    if not tries:
        # A new run may field a new team, and an empty party leaves every card in play until the read below replaces it.
        setattr(task, PARTY, frozenset())
    logger.info("opening the information page to read the team")
    utils._move_and_click(task, *TEAM_PORTRAITS)
    task.sleep(2)
    return True


def apply():
    """Take Sortie to the team once a run, and stop the bot navigating to a screen it is already on."""
    global _patched
    if _patched:
        return

    def install():
        utils_chaos = loaded("utils_chaos")
        if utils_chaos is None:
            return

        # First, so that the marker guard below - which belongs to the other patch entirely - cannot gate it.
        # Composed through `wrap` rather than `replace` because the install runs once per task load and the
        # wrapper carries the handler's own name, which `replace` matches on and would stack a layer per load.
        wrap(utils_chaos, "handle_archive_target_member", reading_in_place, "reading in place")
        # Sortie's list alone, since Chaos makes this trip already.
        insert_before(SORTIE_ANCHOR, handle_open_team, only=("utils_sortie",))

        original = utils_chaos.handle_save_target_member
        if getattr(original, "_en_skips_when_present", False):
            return

        def patched_handle_save_target_member(task):
            if on_member_info_page(task):
                # Declining lets handle_archive_target_member, further down the same list, run this frame.
                logger.info("already on the information page, skipping the menu tap and its two second wait")
                return False
            return original(task)

        patched_handle_save_target_member._en_skips_when_present = True
        replace("handle_save_target_member", patched_handle_save_target_member)

    register(install)
    _patched = True
