"""Olga: stack Fracture and Agony with Rift and Desire, fetch them back with Break Apart, then cash in with Reckoning.

Rift of Severance and Dispersed Desire activate the stacks already on the enemy, and Break Apart & Renew returns the other one to hand.
The generic picker plays Reckoning first before anything is stacked, and rates the 80% Rift and Desire under the plain Reaping Slash.
"""

from src.en.kits.kit import PHASE_ATTACK, Kit, base_name, owned

# The two attacks that stack a damage over time and activate it.
STACKERS = frozenset({"Rift of Severance", "Dispersed Desire"})
# Created from End of the Line, and worth playing only once a stacker has set up the stacks it cashes in.
RECKONING = "Reckoning"
BREAK_APART = "Break Apart & Renew"
# Her plain 100% attack, which every guide cuts from the deck.
REAPING_SLASH = "Reaping Slash"
RIFT = "Rift of Severance"


def stacked(names):
    """Count the stackers among some cards.

    Args:
        names: Canonical card names, from the hand or from what the turns have played.

    Returns:
        How many are Rift of Severance or Dispersed Desire, in any Epiphany.
    """
    return sum(base_name(name) in STACKERS for name in names)


class Olga(Kit):
    """Holds Reckoning until stacks exist, and puts the stackers over Reaping Slash with Break Apart between them."""

    name = "Olga"
    cards = owned("Olga") | {RECKONING}

    def held(self, name, board):
        """Keep Reckoning until a stacker has been played this turn or last, or is in hand to follow it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Reckoning with no stacks to cash in.
        """
        return base_name(name) == RECKONING and not stacked((*board.played, *board.last_turn, *board.hand))

    def worth(self, name, board, base, rate):
        """Rate Rift and Desire as a basic attack at least, and the basic attack under them.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here Reaping Slash's and Rift's.

        Returns:
            The value to plan with.
        """
        card = base_name(name)
        if card in STACKERS:
            return max(base, rate(REAPING_SLASH))
        if card == REAPING_SLASH:
            return min(base, rate(RIFT))
        return base

    def phase(self, name, board, base):
        """Play Reckoning after the stackers, and Break Apart between the first stacker and the next.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        card = base_name(name)
        if card == RECKONING:
            return PHASE_ATTACK + 0.5
        if stacked(board.played):
            # Break Apart returns the stacker just played, so it goes before the next one.
            if card == BREAK_APART:
                return PHASE_ATTACK + 0.25
            if card in STACKERS:
                return PHASE_ATTACK + 0.4
        return base


KIT = Olga()
