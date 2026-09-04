"""Skip the trip to the Combatants screen when the run already starts there.

At the start of a run the bot captures the target combatant's portrait, and to get there
`handle_save_target_member` taps the menu icon and waits two seconds for the page to open. It has no idea
whether the page is open already - its only guard is a "have I done this yet" flag - so starting a run from
that screen costs the tap and the wait for nothing.

`handle_archive_target_member` is registered a few places further down the same list and does the capture once
the page is up. So there is nothing to reimplement: when the page is already showing, decline the frame and
upstream's own handler picks it up immediately.
"""

from ok import Logger

from src.en.handlers import loaded, register, replace

logger = Logger.get_logger(__name__)

# Where the information page draws its member tab icon. Same region `handle_archive_target_member` searches,
# so agreeing with it is the point - if it can find the page, we must not be navigating towards it.
MEMBER_INFO_REGION = (0.005, 0.018, 0.080, 0.343)
MEMBER_INFO_FEATURES = ["memberinfo", "memberinfo2"]

_patched = False


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


def apply():
    """Stop the bot navigating to a screen it is already on."""
    global _patched
    if _patched:
        return

    def install():
        utils_chaos = loaded("utils_chaos")
        if utils_chaos is None:
            return

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
