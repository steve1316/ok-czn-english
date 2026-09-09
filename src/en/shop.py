"""Stop the Dellang shop spending refreshes on a shelf the run cannot afford.

The shop's refresh is free, so `handle_shop` takes it whenever nothing on the shelf matches the user's
priority lists. That is the right call with money in hand and the wrong one without: a captured run sat in
front of a 96 / 96 / 200 shelf holding 29 credits, refreshed until the counter ran out, and left with
nothing. Every refresh in that state is dead time, because no reroll of the shelf can produce something
29 credits will buy.

A floor fixes it. Below the floor the free-refresh button is withheld for the length of one `handle_shop`
call, which is not the same as skipping the click afterwards - by the time upstream has clicked, the frame is
spent. With the button hidden the handler runs out of options and returns False, and `handle_leave`, already
the next entry in `PAGE_HANDLERS`, walks the run out of the shop on the same frame.

The floor is a constant rather than a setting. It is a property of the game's price list, not a preference:
the cheapest thing the shop stocks sits above it, so anything at or under the floor buys nothing whatever the
shelf rerolls into.

This patches `utils.handle_shop` rather than the handler list, because `src/en/rewards.py` wraps the same
handler by reading it back off the module. Going through the module attribute means that wrapper composes
over this one instead of replacing it, so the order in `src/globals.py` - this before rewards - is what keeps
both changes alive.
"""

from ok import Logger

from src.en.handlers import loaded, register

logger = Logger.get_logger(__name__)

# Credits at or below which a reroll of the shelf cannot produce anything affordable.
SHOP_FLOOR = 50
# The bottom-left band `handle_shop` scans for its refresh button, as (x1, y1, x2, y2).
REFRESH_REGION = (0.012, 0.892, 0.258, 0.979)
# The caption on that button. `ocr.po` already rewrites the client's "Free" into this literal.
FREE = "免费"
# Marks a handler this module has already wrapped, so a second task load does not wrap it twice.
GUARD = "_en_shop_floor"

_patched = False


def worth_refreshing(credit):
    """Say whether a free refresh can still lead to a purchase.

    Args:
        credit: The credits the run is holding.

    Returns:
        True when the shelf is worth rerolling.
    """
    return credit > SHOP_FLOOR


def free_refresh_box(task):
    """Find the shop's free-refresh button in the current OCR pass.

    Args:
        task: The running task, whose `all_texts` holds that pass.

    Returns:
        The button's box, or None when it is not on screen.
    """
    x1, y1, x2, y2 = REFRESH_REGION
    for box in getattr(task, "all_texts", None) or []:
        if FREE not in box.name:
            continue
        center_x = (box.x + box.width / 2) / task.width
        center_y = (box.y + box.height / 2) / task.height
        if x1 <= center_x <= x2 and y1 <= center_y <= y2:
            return box
    return None


def refusing_free_refresh(handler, credit_of):
    """Wrap `handle_shop` so it cannot spend a refresh the credits can never use.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        credit_of: Reads the run's current credits from the task.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        # Only the shop screen draws this button, so its absence is the cheap way to skip every other frame
        # without reading credits or repeating upstream's page detection.
        free = free_refresh_box(task)
        if free is None:
            return handler(task)
        credit = credit_of(task)
        if worth_refreshing(credit):
            return handler(task)
        logger.info(f"holding {credit} credits, so the free refresh is withheld and the shop is left")
        before = task.all_texts
        task.all_texts = [box for box in before if box is not free]
        try:
            return handler(task)
        finally:
            task.all_texts = before

    wrapped.__name__ = handler.__name__
    setattr(wrapped, GUARD, True)
    return wrapped


def apply():
    """Withhold the shop's free refresh when the credits cannot use it."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None or getattr(utils.handle_shop, GUARD, False):
            return
        utils.handle_shop = refusing_free_refresh(utils.handle_shop, utils._get_current_credit)
        logger.info(f"shop will not refresh at or below {SHOP_FLOOR} credits")

    register(install)
    _patched = True
