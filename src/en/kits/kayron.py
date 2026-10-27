"""Kayron: exhaust every Futility first, then cash in with Black Hole.

Black Hole hits harder for each Futility exhausted over the whole battle. The generic picker buys it ahead of the Futility cards and plays it
first, so it lands before the exhausts that would have powered it.
"""

from src.en.kits.kit import Kit, base_name, owned

# Cards that exhaust when played, or create Futility to be exhausted, so they all go before Black Hole.
EXHAUSTERS = frozenset({"Futility", "Echo of Futility", "Echoes of True Abyss"})
BLACK_HOLE = "Black Hole"


class Kayron(Kit):
    """Holds Black Hole until nothing is left in hand to exhaust."""

    name = "Kayron"
    cards = owned("Kayron")

    def held(self, name, board):
        """Keep Black Hole while a Futility or a card that makes one is in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a plain Black Hole with exhausting still to do.
        """
        # Black Hole with an Epiphany can be a mid-combo card instead, so only the plain one waits.
        return name == BLACK_HOLE and any(base_name(other) in EXHAUSTERS for other in board.hand)


KIT = Kayron()
