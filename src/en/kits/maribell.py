"""Maribell: fire Shelter Strike last, after her shields.

Shelter Strike deals Fixed Damage equal to the Shield she owns, and Shield does not carry over to the next turn.
The generic picker rates it as a flat 100% attack and plays it before her shield skills, so it hits an empty Shield.
"""

from src.en.kits.kit import PHASE_OTHER, Kit, base_name, count, owned

STRIKE = "Shelter Strike"
# Cards that give her Shield, so Strike has something to deal.
SHIELDERS = frozenset({"Shelter Defense", "Shelter Hold", "Oh... I see.", "Maribell Shelter MK.II", "Resolute Blitz"})
# The attacks Strike is raised above once Shield is up.
RIVALS = ("Resolute Blitz", "Maribell Shelter MK.II")


class Maribell(Kit):
    """Holds Shelter Strike until a shield is up, then plays it last and rates it as her main damage."""

    name = "Maribell"
    cards = owned("Maribell")
    # After her other skills, and so after the shield attacks that sit in the attack phase.
    places = {STRIKE: PHASE_OTHER + 0.5}

    def held(self, name, board):
        """Keep Shelter Strike while no shield is up and one is still in hand to play first.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Strike that would hit an empty Shield.
        """
        return base_name(name) == STRIKE and not count(board.played, SHIELDERS) and count(board.hand, SHIELDERS)

    def worth(self, name, board, base, rate):
        """Rate Shelter Strike above her other attacks once a shield has been played this turn.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the rival attacks'.

        Returns:
            The value to plan with.
        """
        if base_name(name) == STRIKE and count(board.played, SHIELDERS):
            return max(base, *(rate(rival) + 1 for rival in RIVALS))
        return base


KIT = Maribell()
