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


def triggers(names):
    """Find a card in hand that fires Vulture Ejection when played.

    Args:
        names: Canonical names of the cards in hand.

    Returns:
        True when one costs 2 or more, not counting an Ejection, and an X-cost card is -1 so it never counts.
    """
    return any(base_name(name) != EJECTION and TRIGGER_COST <= CARD_COST.get(base_name(name), 0) for name in names)


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
            True for an Ejection that a 2-cost card, or Aquila, would fire for free.
        """
        return base_name(name) == EJECTION and (triggers(board.hand) or count(board.hand, {AQUILA}) > 0)

    def phase(self, name, board, base):
        """Play Aquila ahead of the other attacks while an Ejection is in hand, so the Ejection is still there for its bonus.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == AQUILA and any(base_name(other) == EJECTION for other in board.hand):
            return PHASE_ATTACK - 0.5
        return super().phase(name, board, base)


KIT = Khalipe()
