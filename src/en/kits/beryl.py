"""Beryl: let Charged Shot grow in hand, and make Heavy Weapons Specialist's new card before attacking.

Charged Shot is Retain and gains damage for every turn it is held, and Heavy Weapons Specialist creates a cheap Opening Found or Charged Shot.
The generic picker spends two points on Charged Shot at once as her top attack, and plays Heavy Weapons Specialist after the attacks.
"""

from src.en.kits.kit import PHASE_SETUP, Kit, base_name, owned

CHARGED_SHOT = "Charged Shot"
# Creates the card the attacks then use, so it goes before them.
SPECIALIST = "Heavy Weapons Specialist"


class Beryl(Kit):
    """Ranks Charged Shot last so cheaper cards take the points, and sets up with Heavy Weapons Specialist."""

    name = "Beryl"
    cards = owned("Beryl")
    places = {SPECIALIST: PHASE_SETUP}

    def worth(self, name, board, base, rate):
        """Spend Charged Shot only on points no other card wants.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return 0 if base_name(name) == CHARGED_SHOT else base


KIT = Beryl()
