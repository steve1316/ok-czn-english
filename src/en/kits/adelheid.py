"""Adelheid: set up the Blessing draws, spend Garden of Secrets, and keep Doggie (Pack) until there is a pack of them.

Once Upon A Time blesses cards in the draw pile and Protect Us draws a Blessing card for the next two activated, so the first goes first.
The generic picker plays the two setup cards in hand order, rates Garden of Secrets below Truth Behind A Story, and plays each free Doggie at once.
"""

from src.en.kits.kit import PHASE_SETUP, Kit, base_name, owned

# Blesses cards in the draw pile, so it goes before Protect Us has Blessing cards to draw.
ONCE_UPON = "Once Upon A Time"
GARDEN = "Garden of Secrets"
# Her best attack, which Garden of Secrets is priced against.
TRUTH = "Truth Behind A Story"
# The free Doggie variant that waits for others, per the design note.
PACK = "Doggie (Pack)"
# Doggie (Pack) cards that must be in hand before one is played.
PACK_SIZE = 2


class Adelheid(Kit):
    """Orders her setup cards, prices Garden of Secrets as a top spend, and holds Doggie (Pack) until two are in hand."""

    name = "Adelheid"
    # The Doggie and Teddy tokens are created, so they have no owner and are named here.
    cards = owned("Adelheid") | {"Doggie", "Teddy"}
    places = {ONCE_UPON: PHASE_SETUP - 0.5}

    def held(self, name, board):
        """Keep a Doggie (Pack) until enough of them are in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Doggie (Pack) that would be played alone.
        """
        return name.startswith(PACK) and sum(card.startswith(PACK) for card in board.hand) < PACK_SIZE

    def worth(self, name, board, base, rate):
        """Price Garden of Secrets at least as high as her best attack.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here Truth Behind A Story's.

        Returns:
            The value to plan with.
        """
        if base_name(name) == GARDEN:
            return max(base, rate(TRUTH))
        return base


KIT = Adelheid()
