"""Choose the card an Epiphany goes on in Sortie, and the variant it takes in either mode.

Upstream sparks only the cards on the user's Epiphany list and presses Skip when none is offered, which Sortie's empty default does at every
Epiphany. Its variant pick knows nothing of Divine Epiphanies or the build preset's pins, and with no listed variant offered it picks at random.
"""

import re
import time

from ok import Logger

from src.en import cards, piles
from src.en.game_text import DESCRIPTIONS, DIVINE_EPIPHANIES
from src.en.handlers import StandIn, loaded, register, standing_in, wrap
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

# The mode this chooses in. Chaos leaves the choice to the build preset's pins and the user's list.
SORTIE_MODE = "SortieMode"
# The prompts that spark an Epiphany, as upstream's `select_card` names them.
ACTIONS = ("闪光", "灵光")
# The variant lines that give or save AP: "Gain # AP", "# AP next turn" and "Reduce Cost of this card by #". Most are Divine Epiphany lines
# too, so they also split two Divine variants. Unlike `cards.AP_GAIN` these are unanchored, since the reader runs words together.
AP_LINES = (re.compile(r"Gain\s*(\d+)\s*AP", re.I), re.compile(r"(\d+)\s*AP\s*(?:on\s*the\s*)?next\s*turn", re.I),
            re.compile(r"Reduce\s*Cost\s*of\s*this\s*card\s*by\s*(\d+)", re.I))
# Where a Divine Epiphany screen names its god, as "Epiphany: Diallos". An ordinary Epiphany screen has no caption there.
GOD_REGION = (0.3, 0.82, 0.7, 0.95)
# How long after a variant tap the screen is left to answer. The result or the Faint Memory notice took 0.9-2.5s to draw, and a
# second tap in that gap lands above the notice and dismisses it.
TAP_SETTLE_SECONDS = 3.0
# The task attribute holding when the last variant tap went out.
TAPPED_AT = "_epiphany_variant_tapped_at"
# Names each change in the shared record of what a function already carries.
TAG = "own Epiphany choice"
VARIANT_TAG = "Epiphany variant choice"

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
    """Order the cards on one page by which an Epiphany should go on first.

    Args:
        offered: The cards `recognize_cards_in_deck` found, which `pins` has already narrowed to the pinned ones when there are any.

    Returns:
        Their names as read, best first, in the order offered where nothing tells them apart.
    """
    return [card["name"] for card in sorted(offered, key=lambda card: (sparked(card["name"]), -cards.strength(cards.features(card["name"]))))]


def choosing(select_card, utils):
    """Wrap `select_card` so a Sortie Epiphany is always spent, on the user's listed card when one is offered.

    Args:
        select_card: The function to wrap, upstream's or another patch's.
        utils: The module holding `recognize_cards_in_deck`.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        if action not in ACTIONS or type(task).__name__ != SORTIE_MODE:
            return select_card(task, card_names, count=count, action=action)
        names = list(card_names or [])
        configured = len(names)
        original = utils.recognize_cards_in_deck

        def listing(*args, **kwargs):
            offered = original(*args, **kwargs)
            names[configured:] = ranked(offered)
            logger.info(f"Epiphany goes on the first of {names[configured:]} unless a listed card is offered")
            return offered

        with standing_in(utils, recognize_cards_in_deck=listing):
            return select_card(task, names, count=count, action=action)

    return wrapped


def ap_gain(card):
    """Read how much AP a variant gives or saves.

    Args:
        card: A card dict from `recognize_cards`.

    Returns:
        The largest number on one of its `AP_LINES`, or 0 when it has none.
    """
    text = card.get("description") or ""
    return max((int(number) for line in AP_LINES for number in line.findall(text)), default=0)


def god_of(task):
    """Read which god a Divine Epiphany screen belongs to.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        The god's name as `DIVINE_EPIPHANIES` keys it, or None on an ordinary Epiphany screen.
    """
    return next((god for god in DIVINE_EPIPHANIES if text_in_region(task, f"Epiphany: {god}", GOD_REGION)), None)


def divine(card, god):
    """Say whether a variant on offer carries a Divine Epiphany.

    Only the god's own lines count. Ordinary variants share wording with `DIVINE_SHARED`, such as "Morale 1" and "1 Tenacity Damage".

    Args:
        card: A card dict from `recognize_cards`.
        god: The screen's god, from `god_of`, or None on an ordinary Epiphany screen.

    Returns:
        True when its text holds one of that god's lines under the card's own wording.
    """
    if god is None:
        return False
    name, text = cards.canonical(card["name"]), card.get("description") or ""
    return any(line in DIVINE_EPIPHANIES[god] for line in piles.divine_lines(text, piles.closest_version(name, text)))


class FirstBest(StandIn):
    """Stands in for `random` so upstream's random variant pick takes the one giving the most AP, the first offered on a tie."""

    def choice(self, offered):
        """Take the variant with the most AP from the cards upstream would pick among.

        Args:
            offered: The sequence upstream passes to `random.choice`.

        Returns:
            The first card with the most AP, or the real random choice for anything that is not a list of cards.
        """
        if not offered or not all(isinstance(card, dict) for card in offered):
            return self.original.choice(offered)
        best = max(offered, key=ap_gain)
        # One card is a pick `choosing_variant` already made and logged.
        if len(offered) > 1:
            logger.info(f"no listed Epiphany variant offered, so the one giving {ap_gain(best)} AP goes: {best.get('description')}")
        return best


def choosing_variant(handler, utils):
    """Wrap `handle_view_original` so a Divine Epiphany is taken first, then a pinned variant, then the user's list, then the most AP.

    A Divine or pinned winner is the only card upstream is shown, which puts it ahead of the user's list. Otherwise every card is, and
    upstream's own list match stands, with `FirstBest` in place of its random fallback. A tap within `TAP_SETTLE_SECONDS` of the last is
    held back, and the frame is still claimed.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding `recognize_cards` and `random`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original, tap = utils.recognize_cards, utils._move_and_click
        god = god_of(task)

        def ranked_offer(*args, **kwargs):
            offered = original(*args, **kwargs) or []
            for reason, outranks in ((f"{god}'s Divine Epiphany", lambda card: divine(card, god)), ("pinned", lambda card: card.get("pinned"))):
                ahead = [card for card in offered if outranks(card)]
                if ahead:
                    card = max(ahead, key=ap_gain)
                    logger.info(f"Epiphany variant is {reason}, so it goes: {card.get('description')}")
                    return [card]
            return offered

        # Named after the handler, since upstream logs its caller's name with every tap.
        def handle_view_original(task_, x, y):
            if time.monotonic() - (getattr(task_, TAPPED_AT, None) or float("-inf")) < TAP_SETTLE_SECONDS:
                logger.debug("Epiphany variant was tapped moments ago, so the screen is left to answer")
                return
            setattr(task_, TAPPED_AT, time.monotonic())
            tap(task_, x, y)

        with standing_in(utils, recognize_cards=ranked_offer, random=FirstBest(utils.random), _move_and_click=handle_view_original):
            return handler(task)

    return wrapped


def install(utils):
    """Choose a card for every Sortie Epiphany, and the variant for every Epiphany.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is not None:
        wrap(utils, "select_card", lambda select_card: choosing(select_card, utils), TAG)
        wrap(utils, "handle_view_original", lambda handler: choosing_variant(handler, utils), VARIANT_TAG)


def apply():
    """Spend every Sortie Epiphany rather than skip it, and take the best variant on offer."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
