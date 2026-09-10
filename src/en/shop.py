"""Stop the Dellang shop spending refreshes on a shelf the run cannot afford.

The shop's refresh is free, so `handle_shop` takes it whenever nothing on the shelf matches the user's
priority lists. That is right with money in hand and wrong without: a captured run sat in front of a
96 / 96 / 200 shelf holding almost nothing, refreshed until the counter ran out, and left with nothing anyway.
No reroll can produce something the run can pay for, so every refresh in that state is dead time.

Below the floor the free-refresh button is withheld for one `handle_shop` call, which is not the same as
skipping the click afterwards - by the time upstream has clicked, the frame is spent. With the button hidden
the handler runs out of options and returns False, and `handle_leave`, already the next entry in
`PAGE_HANDLERS`, walks the run out on the same frame. The floor is a constant rather than a setting, set where
the run has been asked to give up rather than where a purchase becomes possible, since rerolling costs nothing
but time.

`handlers.wrap` puts the wrapper both on the module and in the handler lists, which is what lets it compose
with `src/en/rewards.py`: that module rebuilds this handler's list entry by reading it back off the module, so
a wrapper living only in the list would be quietly dropped. Rewards renames what it builds, so it has to run
after this one - that ordering is why `src/globals.py` applies them in the order it does.
"""

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

# The fewest credits still worth rerolling the shelf for. Inclusive: holding exactly this much, the run
# rerolls. Below it every refresh is dead time, because nothing a reroll produces can be paid for.
SHOP_FLOOR = 29
# The bottom-left band `handle_shop` scans for its refresh button, as (x1, y1, x2, y2).
REFRESH_REGION = (0.012, 0.892, 0.258, 0.979)
# The caption on that button. `ocr.po` already rewrites the client's "Free" into this literal.
FREE = "免费"
# Names this change in the shared record of what a function already carries.
TAG = "shop floor"

_patched = False


def free_refresh_box(task):
    """Find the shop's free-refresh button in the current OCR pass.

    Args:
        task: The running task, whose `all_texts` holds that pass.

    Returns:
        The button's box, or None when it is not on screen.
    """
    return text_in_region(task, FREE, REFRESH_REGION)


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
        if credit >= SHOP_FLOOR:
            return handler(task)
        logger.info(f"holding {credit} credits, so the free refresh is withheld and the shop is left")
        with standing_in(task, all_texts=[box for box in task.all_texts if box is not free]):
            return handler(task)

    return wrapped


def install(utils):
    """Wrap the shop handler wherever the run reaches it.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_shop",
         lambda handler: refusing_free_refresh(handler, utils._get_current_credit), TAG)


def apply():
    """Withhold the shop's free refresh when the credits cannot use it."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
