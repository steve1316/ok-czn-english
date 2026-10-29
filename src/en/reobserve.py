"""Re-observe the Chaos start page until its modifiers avoid the blacklist, as far as the event currency allows.

Upstream's `handle_season_chaos_initial_page` re-observes only for a low Save Data Storage Limit, and finds the page by its
Chinese title and button. Neither is ever read on the Global client, so a run starts on whatever modifiers it was dealt.
"""

import re

from ok import Logger

from src.en.handlers import loaded, register, wrap
from src.en.screen import in_region, lines_in, text_in_region

logger = Logger.get_logger(__name__)

# This fork's settings, with English keys since upstream ships neither.
REOBSERVE = "Re-observe Bad Modifiers"
MODIFIER_BLACKLIST = "Modifier Blacklist"
# Every penalty family in the client's `zero_system_eff` table (zero_orb_penalty_001-027), as the panel tags them.
# The table names two families differently from the panel: Retribution shows as Revenge, Carelessness as Neglect.
MODIFIERS = ["Anxiety", "Elite", "Gangrene", "Harden", "Loss", "Neglect", "Plague", "Rage", "Revenge", "Tyrant"]
# How OCR's casing of a tag maps back to its family.
FAMILY_OF = {name.casefold(): name for name in MODIFIERS}
DEFAULT_BLACKLIST = ["Anxiety", "Plague"]
# Upstream's minimum Save Data Storage Limit, which picks the run on the same button.
SAVE_LIMIT_KEY = "存储数据保存上限大于多少"
SAVE_LIMIT = re.compile(r"(?:Save Data Storage Limit|存储数据保存上限)\D*(\d+)", re.I)
# A modifier line opens with its tag, bracketed or not: "[Plague 1] Decrease Max HP" or "Tyrant 2: Increase Attack".
# The level is required, so a wrapped line like "monsters in Elite and Boss Areas" is not read as the Elite modifier.
TAG = re.compile(r"^\W*\[?([a-z]+) ?\d", re.I)
# The page title, read as "Chaos" or glued to "Season Info", where upstream reads it.
TITLE = "Chaos"
TITLE_REGION = (0.075, 0.014, 0.305, 0.090)
# The button, its cost beside it at (0.955, 0.794), and the event currency held at (0.846, 0.048).
BUTTON = "Re-observe"
BUTTON_REGION = (0.659, 0.715, 0.993, 0.851)
COST_REGION = (0.90, 0.76, 0.99, 0.83)
CURRENCY_REGION = (0.80, 0.02, 0.88, 0.08)
# The bonus and modifier lines under the run's name, where upstream reads the save limit.
PANEL_REGION = (0.684, 0.308, 0.982, 0.754)
# Long enough for the panel to redraw, so the next frame reads the new modifiers rather than the old ones fading out.
REDRAW_SECONDS = 2
# Names this change in the shared record of what a function already carries.
TAG_NAME = "modifier blacklist"

_patched = False


def modifiers_in(names):
    """Pick out the modifier families tagged in the panel's text.

    Args:
        names: The OCR text of each box in the panel.

    Returns:
        Each family from `MODIFIERS` that opens a box, in reading order.
    """
    matches = (TAG.match(name) for name in names)
    return [FAMILY_OF[match.group(1).casefold()] for match in matches if match and match.group(1).casefold() in FAMILY_OF]


def number_in(task, region):
    """Read the first whole number OCR found in a region.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: A `(left, top, right, bottom)` tuple in screen fractions.

    Returns:
        The number, or None when no box there is only digits.
    """
    for box in task.all_texts:
        digits = box.name.strip().replace(",", "")
        if digits.isdigit() and in_region(box, region, task.width, task.height):
            return int(digits)
    return None


def reasons_to_reobserve(task, utils_chaos):
    """Say what is wrong with the run on offer.

    Args:
        task: The running task, on the Chaos start page.
        utils_chaos: The loaded `utils_chaos` module, for its config reader.

    Returns:
        One line per reason to re-observe, empty when the run can be entered.
    """
    panel = [box.name for box in task.all_texts if in_region(box, PANEL_REGION, task.width, task.height)]
    modifiers = modifiers_in(panel)
    limit = SAVE_LIMIT.search(lines_in(task, PANEL_REGION))
    logger.debug(f"Chaos start page: modifiers={modifiers}, save limit={limit.group(1) if limit else 'unread'}")

    reasons = []
    required = int(utils_chaos._get_config_value(task, SAVE_LIMIT_KEY, 120))
    if limit and int(limit.group(1)) < required:
        reasons.append(f"Save Data Storage Limit {limit.group(1)} is below {required}")
    if utils_chaos._get_config_value(task, REOBSERVE, True):
        blacklist = utils_chaos._get_config_value(task, MODIFIER_BLACKLIST, DEFAULT_BLACKLIST)
        banned = [name for name in modifiers if name in blacklist]
        if banned:
            reasons.append(f"blacklisted {', '.join(banned)}")
    return reasons


def reobserving(handler, utils_chaos):
    """Wrap `handle_season_chaos_initial_page` so the Global client's start page is re-observed for its modifiers too.

    Declining leaves the page to `handle_enter`, the next handler in `PAGE_HANDLERS`, which starts the run.

    Args:
        handler: The handler to wrap, upstream's or another patch's. Still run where the English button is not on screen.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        button = text_in_region(task, BUTTON, BUTTON_REGION)
        if button is None or text_in_region(task, TITLE, TITLE_REGION) is None:
            return handler(task)
        reasons = reasons_to_reobserve(task, utils_chaos)
        if not reasons:
            return False
        currency, cost = number_in(task, CURRENCY_REGION), number_in(task, COST_REGION)
        if currency is None or cost is None or currency < cost:
            task.log_info(f"Would re-observe ({'; '.join(reasons)}), but holding {currency} for a cost of {cost}, so entering as is")
            return False
        task.log_info(f"Re-observing for {cost} of {currency}: {'; '.join(reasons)}")
        task.click_box(button)
        task.sleep(REDRAW_SECONDS)
        return True

    return wrapped


def install(utils_chaos):
    """Wrap the Chaos start page handler wherever the run reaches it.

    Args:
        utils_chaos: The loaded `utils_chaos` module, or None when it is not importable yet.
    """
    if utils_chaos is None:
        return
    wrap(utils_chaos, "handle_season_chaos_initial_page", lambda handler: reobserving(handler, utils_chaos), TAG_NAME)


def apply():
    """Re-observe the Chaos start page for its modifiers and save limit."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils_chaos")))
    _patched = True
