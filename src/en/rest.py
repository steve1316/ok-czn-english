"""Let a run use the safe zone it reaches, even when it was started partway through a floor.

Upstream rests, meditates or buys a Sortie Epiphany only while `node_status["flash_or_rest"]` is set, and enters
the Dellang shop only while `node_status["shop"]` is. It sets both on the route selection screen and clears each
once it is spent - but every fresh status starts with both off, so a run started anywhere else walks past them.
Its Sortie copy of the rest handler also never looks for the free Epiphany icon that the Chaos one clicks.
"""

import re

from ok import Logger

from src.en.handlers import insert_before, loaded, register, wrap
from src.en.screen import centre_of, text_in_region

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "rest from the start"
SHOP_TAG = "shop from the start"
SHOP_DECIDED_TAG = "shop decided on sight"
OFFERED_TAG = "rest on an offered interaction"
# Upstream's flag for "this rest area has not been used yet".
FLAG = "flash_or_rest"
# Upstream's flag for "enter the shop at this safe zone", and the setting the route screen copies into it.
SHOP = "shop"
SHOP_SETTING = "进入商店"
# What a fresh status holds for `SHOP` until a handler that can read the setting fills it in. Falsy, so upstream
# reading it before then still sees "do not enter".
UNDECIDED = None
# The count the safe zone prints along its bottom edge, as "Available Safe Zone Interactions: 1". Matched
# loosely because only the number is load bearing, and read as text rather than at a point because the line
# moves with its own length. Shops are exempt from the count, which is why only rest and meditate consult it.
INTERACTIONS = re.compile(r"safe\s*zone\s*interactions\W*?(\d+|[|!lIi'])", re.I)
# What OCR has read a lone "1" as at the end of that line: "Interactions:'". Only a read 0 means none are left.
ONE_GLYPHS = "|!lIi'"
# The game's own warning on leaving a safe zone unused, read in English off the Global client. Its Cancel stays, and it is the one sure sign
# an interaction is still going spare when the count above was misread.
UNUSED_WARNING = "not yet used a Safe Zone interaction"
WARNING_REGION = (0.1, 0.25, 0.9, 0.65)
CANCEL = "取消"
CANCEL_REGION = (0.1, 0.5, 0.5, 0.85)
# Rest's own "Unusable" caption, read under the dimmed warning in the band upstream reads Rest's "Free" from. OCR has dropped the U.
REST_UNUSABLE = "nusable"
REST_REGION = (0.154, 0.602, 0.359, 0.847)
# The handler that would otherwise press the warning's Confirm.
CONFIRM_ANCHOR = "handle_center_confirm"
# The handler each mode gates a safe zone on, by the module that defines it. Chaos rests through `utils`,
# Sortie through its own copy, and Story has neither.
GATED_ON_FLAG = {"utils": "handle_rest", "utils_sortie": "handle_rest_sortie"}
# Every handler that reads `SHOP`: the two safe zone screens that offer the shop, and the shop itself.
READS_SHOP = (*GATED_ON_FLAG.items(), ("utils", "handle_shop"))
# The camp's free Epiphany icon and where to look for it, as `handle_rest` searches.
FREE_EPIPHANY = ["special_flash_luosi", "special_flash_luosi2"]
FREE_EPIPHANY_REGION = (0.219, 0.208, 0.786, 0.814)

_patched = False


def ready_to_rest(original_initial_node_status):
    """Wrap upstream's status builder so every fresh status allows the next rest area.

    Upstream builds a fresh status here on Start, on entering a run and on clearing a floor, and looks the
    builder up on its own module each time, so wrapping it covers all three.

    Args:
        original_initial_node_status: Upstream's `_initial_node_status`.

    Returns:
        The wrapped builder.
    """
    def initial_node_status():
        status = original_initial_node_status()
        status[FLAG] = True
        return status

    return initial_node_status


def shop_undecided(original_initial_node_status):
    """Wrap upstream's status builder so every fresh status leaves the shop to the user's setting.

    The builder has no task to read the setting from, so it only marks the shop undecided.

    Args:
        original_initial_node_status: Upstream's `_initial_node_status`.

    Returns:
        The wrapped builder.
    """
    def initial_node_status():
        status = original_initial_node_status()
        status[SHOP] = UNDECIDED
        return status

    return initial_node_status


def deciding_the_shop(original, utils):
    """Wrap a handler that reads `SHOP` so an undecided shop is settled from the user's setting first.

    Args:
        original: The upstream handler.
        utils: Upstream's `utils` module, for its `_get_config_value`.

    Returns:
        The wrapped handler.
    """
    def handler(task):
        status = getattr(task, "node_status", None)
        if status is not None and SHOP in status and status[SHOP] is UNDECIDED:
            status[SHOP] = bool(utils._get_config_value(task, SHOP_SETTING, False))
            logger.info(f"run started off the route screen, so node_status['shop']={status[SHOP]} from Enter Shop")
        return original(task)

    return handler


def interactions_left(task):
    """Read how many safe zone interactions the game says are still going spare.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        The count, or None when the line is not on screen - which is any non-safe-zone screen, and a
        Chinese client, where upstream's own flag stays in charge.
    """
    for box in getattr(task, "all_texts", None) or []:
        found = INTERACTIONS.search(box.name)
        if found:
            count = found.group(1)
            return 1 if count in ONE_GLYPHS else int(count)
    return None


def taking_the_offered_interaction(original):
    """Wrap a safe zone handler so an interaction the game is offering is one upstream will spend.

    The route screen is the only thing that re-arms the flag, so a run that does not pass through it spends the
    flag on its first rest area and never gets it back: one measured run went 6.5 minutes and zero route screens,
    rested once, then skipped three safe zones in a row, each reading the rest feature at over 96% while the game
    still offered an interaction. The game prints the count on screen, so where it says one is going spare
    upstream's answer is overridden for the length of that one call.

    Args:
        original: The upstream handler, which reads `FLAG` to decide whether the area is still unused.

    Returns:
        The wrapped handler.
    """
    def handler(task):
        status = getattr(task, "node_status", None)
        # A stale off is the only thing worth overriding. With the flag already on upstream needs no help,
        # which also keeps the screen read off every frame but the ones that were going to skip the area.
        if status is None or status.get(FLAG, False) or not interactions_left(task):
            return original(task)
        status[FLAG] = True
        try:
            return original(task)
        finally:
            # Put back the off this found, so the override lasts one call and never the run. Upstream clears
            # the flag itself when it spends the area, which lands on the same answer.
            if status.get(FLAG, False):
                status[FLAG] = False

    return handler


def handle_unused_warning(task):
    """Cancel the warning about leaving a safe zone unused, and arm the flag so the next frame spends the interaction.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if not text_in_region(task, UNUSED_WARNING, WARNING_REGION):
        return False
    cancel = text_in_region(task, CANCEL, CANCEL_REGION)
    if cancel is None:
        return False
    # With Rest locked nothing can spend the interaction, and Cancel only leads back to Skip and this warning.
    if text_in_region(task, REST_UNUSABLE, REST_REGION):
        task.log_info("Rest is locked in this safe zone, so leaving it unused")
        return False
    status = getattr(task, "node_status", None)
    if isinstance(status, dict):
        status[FLAG] = True
    task.log_info("about to leave a safe zone with an interaction unused, so staying to use it")
    task.click_box(cancel)
    task.sleep(1)
    return True


def free_epiphany_handler(utils):
    """Build the handler for Sortie's list that clicks the camp's free Epiphany icon, as `handle_rest` does.

    Args:
        utils: Upstream's `utils` module, for the `_move_and_click` that `handle_rest` clicks the icon with.

    Returns:
        The handler.
    """
    def handle_free_epiphany(task):
        # Battle frames reach this too, and a search that misses costs ~90ms at 1080p against ~2us for this read. A count of 0 still searches.
        if interactions_left(task) is None:
            return False
        icon = task.find_one(feature_name=FREE_EPIPHANY, box=task.box_of_screen(*FREE_EPIPHANY_REGION))
        if not icon:
            return False
        utils._move_and_click(task, *centre_of(icon, task.width, task.height))
        task.sleep(1)
        return True

    return handle_free_epiphany


def install(utils):
    """Start every fresh run status ready to rest and shop, take an interaction the game is still offering, and take Sortie's free Epiphany.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "_initial_node_status", ready_to_rest, TAG)
    wrap(utils, "_initial_node_status", shop_undecided, SHOP_TAG)
    # `wrap` reads the handler off the module, so a mode that has not been imported yet simply misses and is
    # picked up on the load that imports it.
    for module_name, handler_name in GATED_ON_FLAG.items():
        wrap(loaded(module_name), handler_name, taking_the_offered_interaction, OFFERED_TAG)
    for module_name, handler_name in READS_SHOP:
        wrap(loaded(module_name), handler_name, lambda handler: deciding_the_shop(handler, utils), SHOP_DECIDED_TAG)
    insert_before("handle_rest_sortie", free_epiphany_handler(utils), only=("utils_sortie",))
    insert_before(CONFIRM_ANCHOR, handle_unused_warning)


def apply():
    """Start every fresh run status ready to rest, and take an interaction the game is still offering."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
