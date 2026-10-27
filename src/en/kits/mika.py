"""Mika: spend Action Points on the partner's cards before her own filler.

Experts cut Water Arrow, Water Barrier and Whirlpool from her deck, since the points do more on a partner's cards.
The generic picker rates them as real attacks and heals, level with a partner's Strike, so they take points first.
"""

from src.en.kits.kit import Kit, base_name, owned

# Her filler cards, which only earn points the partner has no use for.
FILLER = frozenset({"Water Arrow", "Water Barrier", "Whirlpool"})
# No guide gives a number, only that partner cards come first, so the filler is cut to half and any partner card of equal rating beats it.
FILLER_SHARE = 0.5


class Mika(Kit):
    """Rates her filler under the partner's cards."""

    name = "Mika"
    cards = owned("Mika")

    def worth(self, name, board, base, rate):
        """Cut a filler card's value so the partner's cards are bought first.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return base * FILLER_SHARE if base_name(name) in FILLER else base


KIT = Mika()
