"""Choose the card an Epiphany goes on in Sortie when none of the cards offered is on the user's list.

Upstream sparks only the cards on the user's Epiphany list and presses Skip when none is offered, which Sortie's empty default does at every
Epiphany. This lists the offered cards after the user's own: a pinned card first, then one the deck read found without an Epiphany, then
the strongest.
"""

from ok import Logger

from src.en import cards
from src.en.game_text import DESCRIPTIONS
from src.en.handlers import loaded, register, wrap

logger = Logger.get_logger(__name__)

# The mode this chooses in. Chaos leaves the choice to the build preset's pins and the user's list.
SORTIE_MODE = "SortieMode"
# The prompts that spark an Epiphany, as upstream's `select_card` names them.
ACTIONS = ("闪光", "灵光")
# Names this change in the shared record of what a function already carries.
TAG = "own Epiphany choice"

_patched = False


def sparked(name):
    """Say whether the last deck read found a card already carrying an Epiphany.

    The prompt's own card text runs its lines together too badly to match, so this goes by the All Piles read.

    Args:
        name: A card name as the prompt read it.

    Returns:
        True when the deck holds a version other than the base. False for a card the deck read missed.
    """
    name = cards.canonical(name)
    return name in cards.DECK and cards.DECK[name] != DESCRIPTIONS.get(name)


def ranked(offered):
    """Order the offered cards by which an Epiphany should go on first.

    Args:
        offered: The cards `recognize_cards_in_deck` found, which `pins` marks `pinned`.

    Returns:
        Their names as read, best first, in the order offered where nothing tells them apart.
    """
    def order(card):
        return not card.get("pinned"), sparked(card["name"]), -cards.strength(cards.features(card["name"]))

    return [card["name"] for card in sorted(offered, key=order)]


def choosing(select_card, utils):
    """Wrap `select_card` so a Sortie Epiphany is always spent, on the user's listed card when one is offered.

    Args:
        select_card: The function to wrap, upstream's or another patch's.
        utils: The module holding the card recognizer.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        if action not in ACTIONS or type(task).__name__ != SORTIE_MODE:
            return select_card(task, card_names, count=count, action=action)
        task.all_texts = utils._simplify_texts(task.ocr())
        picks = ranked(utils.recognize_cards_in_deck(task, page=f"select_card-{action}"))
        if picks:
            logger.info(f"Epiphany goes on the first of {picks} unless a listed card is offered")
        return select_card(task, [*(card_names or []), *picks], count=count, action=action)

    return wrapped


def install(utils):
    """Choose a card for every Sortie Epiphany.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is not None:
        wrap(utils, "select_card", lambda select_card: choosing(select_card, utils), TAG)


def apply():
    """Spend every Sortie Epiphany rather than skip it."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
