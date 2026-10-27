"""Magna: play her Lead Powers before any other card.

Ice Fragment and Storm of Bitter Cold have Lead, a chance their cost is 1 lower when drawn, and the discount is lost once another card is played.
The generic picker plays epiphany and free cards ahead of Powers, which can burn the discount.
"""

from src.en.kits.kit import PHASE_ESCAPE, Kit, base_name, owned

# Her Lead cards, which must be the first card played in the turn.
LEAD = frozenset({"Ice Fragment", "Storm of Bitter Cold"})


class Magna(Kit):
    """Puts her Lead cards ahead of everything while nothing has been played."""

    name = "Magna"
    cards = owned("Magna")

    def phase(self, name, board, base):
        """Send a Lead card to the very front of the turn, while it can still be the first card played.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            A place ahead of every other, else the card's usual one.
        """
        if base_name(name) in LEAD and not board.played:
            return PHASE_ESCAPE - 1
        return base


KIT = Magna()
