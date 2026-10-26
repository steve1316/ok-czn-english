"""Playstyles for the combatants whose cards need more than the generic picker's value per Action Point.

Upstream plays the first hand card a user-typed list names, and `cards.plan` replaces that with damage, shield and draw per
point. Neither knows a kit that wants cards held or played in an order, so each such combatant gets a file here.
"""

from src.en.kits import rossweisse

# Every kit, listed by hand rather than found by scanning the folder, so the packaged build sees each import.
KITS = (rossweisse.KIT,)


def active(names):
    """Find the kits a hand switches on.

    Args:
        names: Every card in hand.

    Returns:
        The kits with a card in hand, in `KITS` order.
    """
    return [kit for kit in KITS if any(kit.claims(name) for name in names)]


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


def held(name, names):
    """Say whether any kit in play wants a card kept in hand.

    Args:
        name: The card in question.
        names: Every card in hand.

    Returns:
        True to keep it.
    """
    return any(kit.held(name, names) for kit in active(names))


def worth(name, names, base, rate):
    """Run a card's value past every kit in play.

    Args:
        name: The card being valued.
        names: Every card in hand.
        base: What the generic picker made of it.
        rate: Gives the generic value of any card by name.

    Returns:
        The value to plan with.
    """
    for kit in active(names):
        base = kit.worth(name, names, base, rate)
    return base


def waiting(names, count):
    """Find a kit that wants the turn to sit for a frame.

    Args:
        names: Every card the hand reads as.
        count: The hand size the hand counter reads.

    Returns:
        The kit, or None when nothing is waiting.
    """
    return next((kit for kit in active(names) if kit.waiting(names, count)), None)
