"""Kayron: exhaust every Futility first, then cash in with Black Hole, and play the team's cards over a Futility with nothing to feed or on the last point.

Black Hole hits harder for each Futility exhausted over the whole battle. The generic picker buys it ahead of the Futility cards and plays it
first, so it lands before the exhausts that would have powered it.
"""

from src.en.game_battle import CARD_COST
from src.en.kits.kit import Kit, base_name, count, owned

# Cards that exhaust when played, or create Futility to be exhausted, so they all go before Black Hole.
EXHAUSTERS = frozenset({"Futility", "Echo of Futility", "Echoes of True Abyss"})
BLACK_HOLE = "Black Hole"
FUTILITY = "Futility"
# A Futility in a hand where it is all Kayron has left is cut to this share, so the team's cards are bought first. Futility rates 100-160,
# so a quarter sits under a partner's weakest 1-AP card at 60, and it still takes points nothing else wants.
LONE_FUTILITY_SHARE = 0.25
# A Futility gives the turn's last point to any other card in hand that can use it.
LAST_POINT = 1


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
        return name == BLACK_HOLE and count(board.hand, EXHAUSTERS) > 0

    def worth(self, name, board, base, rate):
        """Cut a Futility's value when no card of Kayron's in hand follows up on its exhaust, or when another card can take the last point.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, unused here.

        Returns:
            The value to plan with.
        """
        if base_name(name) != FUTILITY:
            return base
        others = [other for other in board.hand if base_name(other) != FUTILITY and not self.held(other, board)]
        last_point = board.action_points <= LAST_POINT and any(0 <= CARD_COST.get(base_name(other), -1) <= board.action_points for other in others)
        if any(self.claims(other) for other in others) and not last_point:
            return base
        return base * LONE_FUTILITY_SHARE


KIT = Kayron()
