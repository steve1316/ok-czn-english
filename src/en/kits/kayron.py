"""Kayron: exhaust every Futility first, then cash in with Black Hole, and play the team's cards over a Futility with nothing to feed.

Black Hole hits harder for each Futility exhausted over the whole battle. The generic picker buys it ahead of the Futility cards and plays it
first, so it lands before the exhausts that would have powered it.
"""

from src.en.kits.kit import Kit, base_name, owned

# Cards that exhaust when played, or create Futility to be exhausted, so they all go before Black Hole.
EXHAUSTERS = frozenset({"Futility", "Echo of Futility", "Echoes of True Abyss"})
BLACK_HOLE = "Black Hole"
FUTILITY = "Futility"
# A Futility in a hand where it is all Kayron has left is cut to this share, so the team's cards are bought first. Futility rates 100-160,
# so a quarter sits under a partner's weakest 1-AP card at 60, and it still takes points nothing else wants.
LONE_FUTILITY_SHARE = 0.25


class Kayron(Kit):
    """Holds Black Hole until nothing is left in hand to exhaust."""

    name = "Kayron"
    # Futility is created in battle, so the data gives it no owner.
    cards = owned("Kayron") | {FUTILITY}

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

    def worth(self, name, board, base, rate):
        """Cut a Futility's value when no card of Kayron's in hand follows up on its exhaust.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, unused here.

        Returns:
            The value to plan with.
        """
        if base_name(name) != FUTILITY or any(self.claims(other) and base_name(other) != FUTILITY for other in board.hand):
            return base
        return base * LONE_FUTILITY_SHARE


KIT = Kayron()
