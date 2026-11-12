"""Keep the Dellang shop from wasting time it cannot spend credits on, and let it read a shelf name the client wraps.

Upstream walks into the shop however few credits the run holds, and its free refresh rerolls whenever nothing on
the shelf matches - dead time when nothing could be paid for. The shelf also wraps long names onto two lines, which
upstream glues in OCR order ("JudgmentInstant"), so no name ever matched them. A negative paid threshold reads as "never".
Upstream also has no way to keep its credits off Monster Cards for removals and equipment.
"""

import sys

from ok import Logger

from src.en.game_quality import MONSTER_CARDS
from src.en.handlers import answering, loaded, register, standing_in, wrap
from src.en.quality import CARD_INDEX
from src.en.rest import GATED_ON_FLAG as SAFE_ZONES
from src.en.screen import in_region, lines_in, text_in_region
from src.en.state import GEAR, say_once

logger = Logger.get_logger(__name__)

# The fewest credits the shop is worth entering or rerolling with. Inclusive: holding exactly this much, the run
# shops. The cheapest thing it sells - a card, a removal or a paid reroll - costs 35, so below it nothing can be bought.
SHOP_FLOOR = 35
# The bottom-left band `handle_shop` scans for its refresh button, as (x1, y1, x2, y2).
REFRESH_REGION = (0.012, 0.892, 0.258, 0.979)
# The caption on that button. `ocr.po` already rewrites the client's "Free" into this literal.
FREE = "免费"
# The Safe Zone's way into the shop, where upstream's `handle_rest` reads and clicks it.
SHOP_ENTRY = "德朗商店"
SHOP_ENTRY_POINT = (0.360, 0.138)
# The stretch of the top bar the run's credits sit in, as (x1, y1, x2, y2). Upstream reads two fixed points at x 0.734 and 0.794, but
# Chaos draws a Faint Memory orb to the right and the number sits at ~0.647, so every shop read 0 and never paid for a removal.
CREDIT_REGION = (0.600, 0.020, 0.820, 0.090)
# The modules that call upstream's credit reader, which `utils_sortie` imports by name.
CREDIT_READERS = ("utils", "utils_sortie")
# Name each change in the shared record of what a function already carries.
TAG = "shop floor"
NAMES_TAG = "whole shelf names"
NEVER_PAID_TAG = "never paid"
ENTRY_TAG = "shop entry floor"
MONSTER_TAG = "monster cards left"
# The paid-refresh threshold. Upstream pays while credits are above it, so -1 would pay on every frame.
PAID_THRESHOLD = "商店刷新信用点阈值"
# The fork's switch for buying Monster Cards in the shop. On by default, which is how upstream shops.
BUY_MONSTER_CARDS = "Buy Monster Cards"

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


def credits_read(task):
    """Read the run's credits off the top bar, telling an unread count apart from zero.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        The largest number read in `CREDIT_REGION`, or None when it held none.
    """
    counts = [int(box.name) for box in getattr(task, "all_texts", None) or []
              if box.name.isdigit() and in_region(box, CREDIT_REGION, task.width, task.height)]
    return max(counts, default=None)


def current_credit(task):
    """Stand in for upstream's `_get_current_credit`, which reads 0 wherever the number is not at its two points.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        The credits, or 0 when none were read, as upstream answers.
    """
    return credits_read(task) or 0


def skipping_poor_shop(handler, utils):
    """Wrap a Safe Zone handler so it does not walk into the shop holding less than the cheapest thing it sells.

    Upstream enters whenever `node_status["shop"]` is set, which happens on every route page. Clearing it only for
    this call's shop branch leaves resting and meditating as they were. An unread count enters as before.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The loaded `utils` module, for its `find_box_at_point`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        status = getattr(task, "node_status", None)
        if not isinstance(status, dict) or not status.get("shop"):
            return handler(task)
        entry = utils.find_box_at_point(task, *SHOP_ENTRY_POINT)
        if entry is None or SHOP_ENTRY not in entry.name:
            return handler(task)
        credit = credits_read(task)
        if credit is not None and credit < SHOP_FLOOR:
            say_once(task, GEAR, f"{credit} credits is under the {SHOP_FLOOR} the shop's cheapest item costs, so the shop is skipped")
            status["shop"] = False
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


def leaving_monster_cards(handler, utils):
    """Wrap `handle_shop` so a Monster Card on the shelf reads as nameless while `BUY_MONSTER_CARDS` is off.

    Upstream skips a nameless item, so the credits stay for a removal, equipment or another card.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The loaded `utils` module, whose `_get_region_text` and `_get_config_value` the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        if utils._get_config_value(task, BUY_MONSTER_CARDS, True):
            return handler(task)
        # Read now, so this sits on top of whichever name reader the outer wrappers put up.
        read_name = utils._get_region_text

        def without_monsters(task, region):
            name = read_name(task, region)
            card = CARD_INDEX.look_up(name)
            if card in MONSTER_CARDS:
                say_once(task, GEAR, f"{card} is a Monster Card and {BUY_MONSTER_CARDS} is off, so the shop leaves it")
                return ""
            return name

        with standing_in(utils, _get_region_text=without_monsters):
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
    for module in filter(None, map(loaded, CREDIT_READERS)):
        module._get_current_credit = current_credit
    wrap(utils, "handle_shop", lambda handler: refusing_free_refresh(handler, current_credit), TAG)
    # Before the whole-name reader, so that one is outermost and this filters the names it reads.
    wrap(utils, "handle_shop", lambda handler: leaving_monster_cards(handler, utils), MONSTER_TAG)
    wrap(utils, "handle_shop", lambda handler: reading_names_whole(handler, utils), NAMES_TAG)
    wrap(utils, "handle_shop", lambda handler: never_paying(handler, utils), NEVER_PAID_TAG)
    for module_name, handler_name in SAFE_ZONES.items():
        wrap(loaded(module_name), handler_name, lambda handler: skipping_poor_shop(handler, utils), ENTRY_TAG)


def apply():
    """Skip or cut short the shop when the credits cannot buy anything, and read wrapped shelf names whole.

    Runs before `src/en/rewards.py`, which renames the list entry it builds - that ordering is why
    `src/globals.py` applies the two in the order it does.
    """
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
