"""Steer the Season 5 Memory screens by the settings in the Season 5 - Memory drawer.

Upstream reads one free-text Memory Card on every Memory screen: it is the Etched Memory to pick, the Processing
option to take and the bonus Refinement holds out for. Left blank, as the Global defaults leave it, a run picks at
random, never processes and always enters End of Memory. A filled Memory Card still wins over everything here.
"""

from ok import Logger

from src.en.events import fold
from src.en.game_data import CARDS
from src.en.handlers import answering, loaded, register, standing_in, wrap

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
# Memory Bonus choice -> the phrase its Processing option carries, matched loosely the way upstream matches. Taken
# from the rip's card text rather than a Global capture of the Processing page, so these are still unconfirmed.
BONUS_PHRASES = {
    "Self Attack%": "Attack to this unit",
    "Team Attack%": "Attack to all allies",
    "Self Damage": "Damage Amount of this unit",
    "Team Damage": "Damage Amount of all allies",
}
BONUSES = [KEEP_BONUS, *BONUS_PHRASES]
# Memory Processing's own choice, and Memory Refinement's check of whether to process before refining.
BONUS_HANDLERS = ("handle_memory_process", "handle_precision_memory_process")
# Name each change in the shared record of what a function already carries.
PICK_TAG = "etched memory priority"
BONUS_TAG = "memory bonus"
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


def holding_bonus(handler, utils_chaos):
    """Wrap a Processing or Refinement handler so it holds out for the chosen Memory Bonus.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils_chaos: The loaded `utils_chaos` module.

    Returns:
        The wrapped handler.
    """
    def chosen_bonus(task, typed):
        return typed or BONUS_PHRASES.get(utils_chaos._get_config_value(task, MEMORY_BONUS, KEEP_BONUS), "")

    def wrapped(task):
        with answering(utils_chaos, MEMORY_CARD, chosen_bonus):
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
    for name in BONUS_HANDLERS:
        wrap(utils_chaos, name, lambda handler: holding_bonus(handler, utils_chaos), BONUS_TAG)
    wrap(utils_chaos, "handle_go_to_memory_end", lambda handler: entering_memory_end(handler, utils_chaos), END_TAG)


def apply():
    """Steer the Memory screens by the Season 5 - Memory settings."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils_chaos")))
    _patched = True
