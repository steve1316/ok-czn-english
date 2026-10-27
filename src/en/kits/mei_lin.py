"""Mei Lin: buff first, Rising Dragon Spire last.

Rising Dragon Spire gets more hits from the cards played before it, and Spirit of the Aromata only buffs cards played after it.
The generic picker plays Spire in hand order among the Strikes and Spirit after every attack, and buys the 2 AP Sovereignty first.
"""

from src.en.kits.kit import PHASE_OTHER, PHASE_SETUP, Kit, base_name, owned

SPIRE = "Rising Dragon Spire"
SOVEREIGNTY = "Flame Dragon's Sovereignty"
GUARDIAN = "Flame Dragon Guardian"
STRIKE = "Strike"
# What Sovereignty costs, to hold its worth under the Strikes' per Action Point.
SOVEREIGNTY_COST = 2


class MeiLin(Kit):
    """Buffs first, spends the Strikes, then the Spire, with Sovereignty and Guardian only on leftover points."""

    name = "Mei Lin"
    cards = owned("Mei Lin")
    # Spirit just after her Jewel in the setup phase, then Spire after the attacks and Sovereignty and Guardian behind it.
    places = {"Spirit of the Aromata": PHASE_SETUP + 0.5, SPIRE: PHASE_OTHER + 0.25, SOVEREIGNTY: PHASE_OTHER + 0.5, GUARDIAN: PHASE_OTHER + 0.75}

    def worth(self, name, board, base, rate):
        """Keep Sovereignty from beating the Strikes and the Spire for points, since the guides cut it from the deck.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the Strike's and the Spire's.

        Returns:
            The value to plan with.
        """
        if base_name(name) == SOVEREIGNTY:
            return min(base, min(rate(STRIKE), rate(SPIRE)) * SOVEREIGNTY_COST - 1)
        return base


KIT = MeiLin()
