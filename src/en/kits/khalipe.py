"""Khalipe: let Vulture Ejection fire free from a 2-cost card instead of paying 3 Action Points for it.

Vulture Ejection fires by itself when a card costing 2 or more is played while it is in hand, and Greatsword Aquila costs 1 more with one in
hand. The generic picker buys Vulture Ejection as a 3-point attack and plays Aquila after other 2-cost cards have already used the Ejection up.
"""

from src.en.game_battle import CARD_COST
from src.en.kits.kit import PHASE_ATTACK, Kit, base_name, count, owned

EJECTION = "Vulture Ejection"
# Costs 1 more with an Ejection in hand, so it is itself the 2-cost card that fires it.
AQUILA = "Greatsword Aquila"
# Cost that fires the Ejection.
TRIGGER_COST = 2


def fires(name):
    """Say whether playing a card fires a Vulture Ejection held in hand.

    Args:
        name: A canonical card name.

    Returns:
        True for Aquila and for any other card costing 2 or more but an Ejection. An X-cost card is -1 so it never counts.
    """
    card = base_name(name)
    return card == AQUILA or (card != EJECTION and TRIGGER_COST <= CARD_COST.get(card, 0))


def triggers(board):
    """Find a card in hand that fires Vulture Ejection and can be played this turn.

    A card some kit holds, like a low Hew, or one dearer than the points left never comes, so it must not keep the Ejection waiting.

    Args:
        board: The `cards.Board` being planned.

    Returns:
        True when such a card is in hand.
    """
    # Imported here since the registry imports this module.
    from src.en import kits
    return any(fires(name) and CARD_COST.get(base_name(name), 0) <= board.action_points and not kits.held(name, board) for name in board.hand)


class Khalipe(Kit):
    """Holds Vulture Ejection for a 2-cost card, and plays Aquila first of them while it still has an Ejection to use."""

    name = "Khalipe"
    cards = owned("Khalipe")

    def held(self, name, board):
        """Keep Vulture Ejection while another card in hand could fire it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for an Ejection that a 2-cost card, or Aquila, would fire for free this turn.
        """
        return base_name(name) == EJECTION and triggers(board)

    def worth(self, name, board, base, rate):
        """Add the Ejection a card fires to its own value, so the card that fires it is bought rather than outbid.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the Ejection's.

        Returns:
            The value to plan with.
        """
        if fires(name) and count(board.hand, {EJECTION}):
            return base + rate(EJECTION)
        return base

    def phase(self, name, board, base):
        """Play Aquila ahead of the other attacks while an Ejection is in hand, so the Ejection is still there for its bonus.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == AQUILA and count(board.hand, {EJECTION}):
            return PHASE_ATTACK - 0.5
        return super().phase(name, board, base)


KIT = Khalipe()
