"""Playstyles for the combatants whose cards need more than the generic picker's value per Action Point.

Upstream plays the first hand card a user-typed list names, and `cards.plan` replaces that with damage, shield and draw per
point. Neither knows a kit that wants cards held or played in an order, so each such combatant gets a file here.
"""

from functools import lru_cache

from src.en.kits.kit import base_name
from src.en.kits import (
    adelheid, amir, anika, arabella, beryl, cassius, chizuru, diana, fei, haru, heidemarie, hilde, hugo, kayron,
    khalipe, lucas, luke, magna, maribell, mei_lin, mika, narja, nia, nine, olga, orlea, owen, rei, renoa, rin, rita,
    rossweisse, selena, sereniel, tenebria, tiphera, tressa, veronica, yuki,
)

# Every kit, listed by hand rather than found by scanning the folder, so the packaged build sees each import.
KITS = (
    rossweisse.KIT, luke.KIT, hugo.KIT, owen.KIT, lucas.KIT, magna.KIT, maribell.KIT, mei_lin.KIT, mika.KIT, narja.KIT,
    nia.KIT, adelheid.KIT, amir.KIT, anika.KIT, arabella.KIT, beryl.KIT, cassius.KIT, chizuru.KIT, diana.KIT, fei.KIT,
    haru.KIT, heidemarie.KIT, hilde.KIT, kayron.KIT, khalipe.KIT, nine.KIT, olga.KIT, orlea.KIT, rei.KIT, renoa.KIT,
    rin.KIT, rita.KIT, selena.KIT, sereniel.KIT, tenebria.KIT, tiphera.KIT, tressa.KIT, veronica.KIT, yuki.KIT,
)


def active(names):
    """Find the kits a hand switches on.

    Args:
        names: Every card in hand.

    Returns:
        The kits with a card in hand, in `KITS` order.
    """
    return switched_on(tuple(names))


# Every hook asks again for every card, and the hand only changes between frames.
@lru_cache(maxsize=64)
def switched_on(names):
    """Find the kits a hand switches on, once per hand.

    Args:
        names: Every card in hand, as a tuple.

    Returns:
        The kits with a card in hand, in `KITS` order.
    """
    return tuple(kit for kit in KITS if any(kit.claims(name) for name in names))


def reading(hand, count):
    """Run the hand reading past every kit it switches on.

    Args:
        hand: Hand cards as `_hand_cards` reads them, with canonical names.
        count: The hand size the hand counter reads.

    Returns:
        The hand, as the kits correct it.
    """
    for kit in active([card["name"] for card in hand]):
        hand = kit.reading(hand, count)
    return hand


def held(name, board):
    """Say whether any kit in play wants a card kept in hand.

    Args:
        name: The card in question.
        board: The `cards.Board` it would be played into.

    Returns:
        True to keep it.
    """
    return any(kit.held(name, board) for kit in active(board.hand))


def worth(name, board, base, rate):
    """Run a card's value past every kit in play.

    Args:
        name: The card being valued.
        board: The `cards.Board` it would be played into.
        base: What the generic picker made of it.
        rate: Gives the generic value of any card by name.

    Returns:
        The value to plan with.
    """
    for kit in active(board.hand):
        base = kit.worth(name, board, base, rate)
    return base


def phase(name, board, base):
    """Run a card's place in the turn past every kit in play.

    Args:
        name: The card being placed.
        board: The `cards.Board` it would be played into.
        base: Where the generic order puts it.

    Returns:
        The phase to sort by.
    """
    for kit in active(board.hand):
        base = kit.phase(name, board, base)
    return base


def fodder(opener, name, board):
    """Say whether any kit in play wants a prompt to give up a card first.

    Args:
        opener: The card whose play raised the prompt, or None when none is known.
        name: A hand card the prompt could take.
        board: The `cards.Board` of the hand on offer.

    Returns:
        True to give it up first.
    """
    return opener is not None and any(kit.fodder(opener, name) for kit in active(board.hand))


def waiting(names, count):
    """Find a kit that wants the turn to sit for a frame.

    Args:
        names: Every card the hand reads as.
        count: The hand size the hand counter reads.

    Returns:
        The kit, or None when nothing is waiting.
    """
    return next((kit for kit in active(names) if kit.waiting(names, count)), None)


def ends_turn(name):
    """Say whether a card is a Finale, which ends the turn on play.

    Args:
        name: A canonical card name.

    Returns:
        True when some kit lists the card, without its Epiphany, as a Finale.
    """
    return any(base_name(name) in kit.finales for kit in KITS)
