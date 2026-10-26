"""Steer the Season 5 Memory screens by the settings in the Season 5 - Memory drawer.

Upstream reads one free-text Memory Card on every Memory screen: the Etched Memory to pick and the Processing reroll to
take, matched as a loose character subsequence. Left blank, as the Global defaults leave it, a run picks at random, never
processes and always enters End of Memory. A filled Memory Card still wins over everything here.
"""

from ok import Logger

from src.en.events import fold
from src.en.game_data import CARDS
from src.en.handlers import answering, loaded, register, standing_in, wrap
from src.en.screen import centre_of, lines_in, text_in_region

logger = Logger.get_logger(__name__)

# Upstream's free-text Memory Card, read on all three Memory screens.
MEMORY_CARD = "指定记忆卡牌"
# This fork's Season 5 settings, with English keys since upstream ships none of them.
ETCHED_MEMORY = "Etched Memory Priority"
MEMORY_BONUS = "Memory Bonus"
ENTER_MEMORY_END = "Enter End of Memory"
# The boss memories the Interior offers, from the game's own card table.
MEMORIES = [name for name in CARDS if name.startswith("Memory: ")]
# Leaves Processing alone, which is what upstream does with a blank Memory Card.
KEEP_BONUS = "(keep)"
# Memory Bonus choice -> its effect as `fold` leaves it, matched as a substring. Upstream's subsequence match cannot tell
# them apart: Memory: Loss's fixed "Damage Amount of Justice Attribute Attack Cards of this unit" holds every one in order.
BONUS_MARKERS = {
    "% Attack to this unit": "attacktothis",
    "% Damage Amount to this unit": "damageamountofthis",
    "% Attack to allies": "attacktoallies",
    "% Damage Amount to allies": "damageamountofallies",
}
BONUSES = [KEEP_BONUS, *BONUS_MARKERS]
# Where upstream reads the Processing title. Memory Refinement's own title holds the same word.
PROCESS_TITLE_REGION = (0.420, 0.072, 0.584, 0.169)
PROCESS_TITLE = "加工记忆"
REFINE_TITLE = "精密加工记忆"
# The three rerolled copies of the etched card across Memory Processing, left to right.
PROCESS_COLUMNS = ((0.140, 0.240, 0.360, 0.840), (0.390, 0.240, 0.610, 0.840), (0.640, 0.240, 0.860, 0.840))
# Memory Processing's Confirm button, which spends one crystal.
CONFIRM = "确认"
CONFIRM_REGION = (0.780, 0.880, 0.940, 0.980)
# The etched card in the middle of Memory Refinement, where upstream reads it.
REFINE_CARD_REGION = (0.366, 0.233, 0.639, 0.900)
# A Memory Card no card can hold, so upstream's Refinement handler presses Memory Processing once it recognises the card.
NO_CARD = "\x00"
# Name each change in the shared record of what a function already carries.
PICK_TAG = "etched memory priority"
PROCESS_TAG = "memory bonus choice"
REFINE_TAG = "memory bonus processing"
END_TAG = "end of memory switch"

_patched = False


def best_memory(priority, cards):
    """Find the highest-priority Etched Memory on offer.

    Args:
        priority: The user's Etched Memory Priority, best first.
        cards: The cards `recognize_cards` read off the selection page.

    Returns:
        The offered card's own name, or "" when none of the list is on offer.
    """
    for wanted in priority:
        for card in cards:
            if fold(wanted) in fold(card.get("name")):
                return card["name"]
    return ""


def picking_memory(handler, utils_chaos):
    """Wrap `handle_memory_card_select` so it takes the best Etched Memory on offer before rerolling.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        offered = []
        original_recognise = utils_chaos.recognize_cards

        def recognised(*args, **kwargs):
            # Upstream reads the cards before the Memory Card, so the answer can be drawn from what is on offer.
            offered[:] = original_recognise(*args, **kwargs)
            return offered

        def best_on_offer(task_, typed):
            return typed or best_memory(utils_chaos._get_config_value(task_, ETCHED_MEMORY, []) or [], offered)

        with answering(utils_chaos, MEMORY_CARD, best_on_offer), standing_in(utils_chaos, recognize_cards=recognised):
            return handler(task)

    return wrapped


def bonus_of(text):
    """Name the Memory Bonus a card's text carries.

    Args:
        text: The card's description, as `lines_in` reads it.

    Returns:
        The `BONUS_MARKERS` choice, or None when the text holds none of them.
    """
    folded = fold(text)
    return next((bonus for bonus, marker in BONUS_MARKERS.items() if marker in folded), None)


def wanted_bonus(task, utils_chaos):
    """Return the chosen Memory Bonus, or None when the setting keeps the card as it is.

    Args:
        task: The running Chaos task.
        utils_chaos: The loaded `utils_chaos` module.
    """
    chosen = utils_chaos._get_config_value(task, MEMORY_BONUS, KEEP_BONUS)
    return chosen if chosen in BONUS_MARKERS else None


def choosing_bonus(handler, utils_chaos):
    """Wrap `handle_memory_process` so it confirms the reroll carrying the chosen Memory Bonus, and skips when none does.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        title = text_in_region(task, PROCESS_TITLE, PROCESS_TITLE_REGION)
        if title is None or REFINE_TITLE in title.name:
            return handler(task)
        wanted = wanted_bonus(task, utils_chaos)
        if wanted is None or utils_chaos._get_config_value(task, MEMORY_CARD, ""):
            return handler(task)
        for column in PROCESS_COLUMNS:
            if bonus_of(lines_in(task, column)) == wanted:
                left, top, right, bottom = column
                task.log_info(f"Memory Processing: taking the reroll with {wanted}")
                utils_chaos._move_and_click(task, (left + right) / 2, (top + bottom) / 2)
                task.sleep(1)
                confirm = text_in_region(task, CONFIRM, CONFIRM_REGION)
                if confirm is not None:
                    utils_chaos._move_and_click(task, *centre_of(confirm, task.width, task.height))
                return True
        task.log_info(f"Memory Processing: no reroll carries {wanted}, keeping the card")
        return handler(task)

    return wrapped


def processing_for_bonus(handler, utils_chaos):
    """Wrap `handle_precision_memory_process` so Memory Refinement presses Processing when the card holds another bonus.

    Only a bonus actually read counts, so a card whose text did not read is never spent on.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def unless_held(task, typed):
        if typed:
            return typed
        wanted = wanted_bonus(task, utils_chaos)
        if wanted is None:
            return ""
        held = bonus_of(lines_in(task, REFINE_CARD_REGION))
        return NO_CARD if held not in (None, wanted) else ""

    def wrapped(task):
        with answering(utils_chaos, MEMORY_CARD, unless_held):
            return handler(task)

    return wrapped


def entering_memory_end(handler, utils_chaos):
    """Wrap `handle_go_to_memory_end` so the switch can leave End of Memory alone.

    Declining leaves the final Settlement to `handle_continue`, the next handler in `PAGE_HANDLERS`, which ends the run.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        if utils_chaos._get_config_value(task, ENTER_MEMORY_END, True):
            return handler(task)
        return False

    return wrapped


def install(utils_chaos):
    """Wrap the Memory handlers wherever the Chaos run reaches them.

    Args:
        utils_chaos: The loaded `utils_chaos` module, or None when it is not importable yet.
    """
    if utils_chaos is None:
        return
    wrap(utils_chaos, "handle_memory_card_select", lambda handler: picking_memory(handler, utils_chaos), PICK_TAG)
    wrap(utils_chaos, "handle_memory_process", lambda handler: choosing_bonus(handler, utils_chaos), PROCESS_TAG)
    wrap(utils_chaos, "handle_precision_memory_process", lambda handler: processing_for_bonus(handler, utils_chaos), REFINE_TAG)
    wrap(utils_chaos, "handle_go_to_memory_end", lambda handler: entering_memory_end(handler, utils_chaos), END_TAG)


def apply():
    """Steer the Memory screens by the Season 5 - Memory settings."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils_chaos")))
    _patched = True
