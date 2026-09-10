"""Skip the trip to the Combatants screen when the run already starts there.

At the start of a run the bot captures the target combatant's portrait, and getting there takes two handlers.
`handle_save_target_member` taps the menu icon and waits two seconds for the page to open. It has no idea
whether the page is open already - its only guard is a "have I done this yet" flag - so starting a run from
that screen costs the tap and the wait for nothing.

`handle_archive_target_member` is registered a few places further down the same list and does the capture once
the page is up. So there is nothing to reimplement for the first tap: when the page is already showing,
decline the frame and upstream's own handler picks it up immediately.

The capture then repeats the mistake one level down. Before reading anything it taps the 3-person icon and
taps the Combatants tab, which on a run started there shuts the page and opens it again for no gain. The log
is plain about the cost: the OCR taken before those two taps and the OCR taken after them list the same sixty
boxes, three seconds apart. Dropping the taps recovers about 1.6s of that, most of it the time `click_box`
spends in its own `after_sleep`. The rest is upstream's two half-second waits and its second OCR, left alone
because removing them would mean owning the read as well as the way in.

Dropping the taps has to be self-verifying, because the information screen has sibling tabs - Partners and
Fate draw names in the same three places - and reading the wrong one would quietly cost the run its portrait.
The proof used is the configured combatant's own name: seeing it at one of the three slots says both that
this is the tab listing combatants and that it is open now. Anything else navigates the long way round, and
the only run that pays the full cost is the run whose round trip would have found nothing either.

What cannot be checked from here is upstream's shape. The two taps are recognised by coordinate and by being
the capture's only box click, both read off a function body with nothing to import, so a rebase moving either
would slip past in silence. `Dropped` is the answer to that: the stand-ins count what they swallowed, and the
wrapper says so when the tally is not the one tap each that upstream makes today.
"""

import dataclasses

from ok import Logger

from src.en.handlers import loaded, register, replace, standing_in, wrap
from src.en.overrides import FARMED_COMBATANT
from src.en.screen import COMBATANT_NAME_POINTS

logger = Logger.get_logger(__name__)

# Where the information page draws its member tab icon. Same region `handle_archive_target_member` searches,
# so agreeing with it is the point - if it can find the page, we must not be navigating towards it.
MEMBER_INFO_REGION = (0.005, 0.018, 0.080, 0.343)
MEMBER_INFO_FEATURES = ["memberinfo", "memberinfo2"]

# Where upstream taps to select the Combatants tab, read off the capture. Check this if a rebase moves it.
COMBATANTS_TAB = (0.201, 0.056)

_patched = False


@dataclasses.dataclass
class Dropped:
    """Counts the taps the stand-ins swallowed, so a capture that has changed shape gets noticed."""

    tab: int = 0   # taps on the Combatants tab that were dropped; upstream makes exactly one
    icon: int = 0  # box clicks that were dropped, all of them the 3-person icon; upstream makes exactly one


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
    """Report whether the Combatants tab is already open on the combatant the run is farming.

    Reading the configured name off one of the three slots proves both halves at once: the tab listing
    combatants is the tab in front of us, and it is showing them now. A sibling tab carries other names, so
    it fails the test and the capture navigates as it always did.

    Args:
        task: The running task.

    Returns:
        True when the farmed combatant is already named on screen.
    """
    utils = loaded("utils")
    if utils is None:
        return False
    target = utils._get_config_value(task, FARMED_COMBATANT, "")
    if not target:
        # Nothing to recognise the tab by, so nothing to be confident about. Upstream handles the unset case
        # by closing the page again, and it is welcome to do that the slow way.
        return False
    for x, y in COMBATANT_NAME_POINTS:
        box = utils.find_box_at_point(task, x, y)
        name = box.name.strip() if box else ""
        # Upstream's own matching rule, so a name accepted here is one its read would accept too.
        if name and (target in name or name in target):
            return True
    return False


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
        if utils_chaos is None or not on_combatants_tab(task):
            return original(task)
        logger.info("already on the Combatants tab, reading the three names without tapping back to it")
        dropped = Dropped()
        # Stood in for rather than reimplemented: everything the capture does after the two taps - the OCR,
        # the name match and the six portrait crops - is upstream's, and none of it changes.
        tab_tap = without_the_tab_tap(utils_chaos._move_and_click, dropped)
        with standing_in(utils_chaos, _move_and_click=tab_tap), \
                standing_in(task, click_box=without_the_icon_tap(dropped)):
            handled = original(task)
        if (dropped.tab, dropped.icon) != (1, 1):
            # Loud on purpose. Both taps are recognised by shape rather than by name, so upstream changing
            # either is invisible until someone reads the log - either a tap it still needed was swallowed,
            # or the skip quietly stopped saving anything.
            logger.warning(f"expected to drop one tab tap and one icon tap, dropped {dropped.tab} and "
                           f"{dropped.icon}: upstream's capture has changed shape, so this skip needs a look")
        return handled

    return handle_archive_target_member


def apply():
    """Stop the bot navigating to a screen it is already on."""
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
