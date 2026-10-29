"""Narja: set up Voracity and Tenacity before the attacks that use them.

Voluntary Control makes the Voracity and Predation that later attack hits spend, and Domain of Voracity raises the Tenacity damage later hits deal.
The generic picker plays Voluntary Control after every attack, Domain among them, and rates her Attack Response filler like a real attack.
"""

from src.en.kits.kit import PHASE_PRIME, Kit, base_name, owned

FILLER = "NA: Attack Response"
# No guide gives a number, only that it comes last, so it is cut to half and any attack of equal rating beats it.
FILLER_SHARE = 0.5


class Narja(Kit):
    """Plays Voluntary Control then Domain ahead of the attacks, and Attack Response only on leftover points."""

    name = "Narja"
    cards = owned("Narja")
    # Voluntary Control, then Domain with the primers, so both come ahead of the attacks they feed.
    places = {"Voluntary Control": PHASE_PRIME - 0.5, "Domain of Voracity": PHASE_PRIME}

    def worth(self, name, board, base, rate):
        """Cut Attack Response's value so real attacks are bought first.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return base * FILLER_SHARE if base_name(name) == FILLER else base


KIT = Narja()
