"""Stop the Dellang shop spending refreshes it cannot use, and let it read a shelf name the client wraps.

The shop's refresh is free, so `handle_shop` takes it whenever nothing on the shelf matches the user's
priority lists - dead time when no reroll could produce something the run can pay for. The shelf also wraps
long names onto two lines, which upstream glues in OCR order ("JudgmentInstant"), so no name ever matched them.
Upstream pays for a reroll above any threshold, so a negative one is read as "never".
"""

import sys

from ok import Logger

from src.en.handlers import answering, loaded, register, standing_in, wrap
from src.en.screen import lines_in, text_in_region
from src.en.state import GEAR, say_once

logger = Logger.get_logger(__name__)

# The fewest credits still worth rerolling the shelf for. Inclusive: holding exactly this much, the run
# rerolls. Below it every refresh is dead time, because nothing a reroll produces can be paid for.
# Where the run is asked to give up, rather than where a purchase becomes possible, since rerolling costs
# nothing but time. A captured run sat in front of a 96 / 96 / 200 shelf holding almost nothing and refreshed
# until the counter ran out.
SHOP_FLOOR = 29
# The bottom-left band `handle_shop` scans for its refresh button, as (x1, y1, x2, y2).
REFRESH_REGION = (0.012, 0.892, 0.258, 0.979)
# The caption on that button. `ocr.po` already rewrites the client's "Free" into this literal.
FREE = "免费"
# Name each change in the shared record of what a function already carries.
TAG = "shop floor"
NAMES_TAG = "whole shelf names"
NEVER_PAID_TAG = "never paid"
# The paid-refresh threshold. Upstream pays while credits are above it, so -1 would pay on every frame.
PAID_THRESHOLD = "商店刷新信用点阈值"

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

    The button is withheld for one `handle_shop` call, which is not the same as skipping the click afterwards - by
    the time upstream has clicked, the frame is spent. With it hidden the handler runs out of options and returns
    False, and `handle_leave`, already the next entry in `PAGE_HANDLERS`, walks the run out on the same frame.

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
            say_once(task, GEAR, f"{credit} credits is over the {SHOP_FLOOR} floor, so the free refresh stands")
            return handler(task)
        say_once(task, GEAR, f"{credit} credits is under the {SHOP_FLOOR} floor, "
                             f"so the free refresh is withheld and the shop is left")
        with standing_in(task, all_texts=[box for box in task.all_texts if box is not free]):
            return handler(task)

    return wrapped


def reading_names_whole(handler, utils):
    """Wrap `handle_shop` so a shelf name wrapped onto two lines is read top line first, with a space between.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The loaded `utils` module, whose `_get_region_text` the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        # Inside `handle_shop`, `_get_region_text` reads only the item names, so the swap reaches nothing else.
        with standing_in(utils, _get_region_text=lines_in):
            return handler(task)

    return wrapped


def never_paying(handler, utils):
    """Wrap `handle_shop` so a negative paid-refresh threshold never pays.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The loaded `utils` module, whose `_get_config_value` the handler reads the threshold through.

    Returns:
        The wrapped handler.
    """
    def unreachable(task, value):
        # Out of reach of any credit count, so upstream's own "not above the threshold" branch declines.
        return sys.maxsize if isinstance(value, int) and value < 0 else value

    def wrapped(task):
        with answering(utils, PAID_THRESHOLD, unreachable):
            return handler(task)

    return wrapped


def install(utils):
    """Wrap the shop handler wherever the run reaches it.

    `handlers.wrap` puts the wrapper both on the module and in the handler lists, which is what lets it compose
    with `src/en/rewards.py`: that module rebuilds this handler's list entry by reading it back off the module,
    so a wrapper living only in the list would be quietly dropped.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_shop", lambda handler: refusing_free_refresh(handler, utils._get_current_credit), TAG)
    wrap(utils, "handle_shop", lambda handler: reading_names_whole(handler, utils), NAMES_TAG)
    wrap(utils, "handle_shop", lambda handler: never_paying(handler, utils), NEVER_PAID_TAG)


def apply():
    """Withhold the shop's free refresh when the credits cannot use it, and read wrapped shelf names whole.

    Runs before `src/en/rewards.py`, which renames the list entry it builds - that ordering is why
    `src/globals.py` applies the two in the order it does.
    """
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
