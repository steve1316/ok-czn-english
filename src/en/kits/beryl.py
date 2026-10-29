"""Beryl: let Charged Shot grow in hand, spend a kept Opening Found, and make Heavy Weapons Specialist's new card before attacking.

Charged Shot gains damage each turn it is kept, an Opening Found kept from last turn has an extra hit for this turn only, and Heavy Weapons
Specialist creates a cheap Opening Found or Charged Shot. The generic picker spends two points on Charged Shot at once, sees no extra hit,
and plays Heavy Weapons Specialist after the attacks.
"""

from src.en.kits.kit import PHASE_SETUP, Kit, base_name, owned, retain_lines

# Grows by its Retain line, which one of its Epiphanies drops.
CHARGED_SHOT = "Charged Shot"
# Its Retain line adds hits for one turn, so a copy kept from last turn is worth a second hit. That also buys it first among the attacks.
OPENING_FOUND = "Opening Found"
KEPT_HITS = 2
# Begins the Retain line that adds the hit. Its Epiphanies cut the cost, add damage or drop the line instead.
ADDS_HITS = "Add "
# Creates the card the attacks then use, so it goes before them.
SPECIALIST = "Heavy Weapons Specialist"


class Beryl(Kit):
    """Ranks Charged Shot last so cheaper cards take the points, spends a kept Opening Found, and sets up with Heavy Weapons Specialist."""

    name = "Beryl"
    cards = owned("Beryl")
    places = {SPECIALIST: PHASE_SETUP}

    def worth(self, name, board, base, rate):
        """Spend Charged Shot only on points no other card wants, and count a kept Opening Found's extra hit.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        card = base_name(name)
        if card == CHARGED_SHOT:
            return 0 if retain_lines(name, board) else base
        if card == OPENING_FOUND and OPENING_FOUND in map(base_name, board.kept) and any(line.startswith(ADDS_HITS) for line in retain_lines(name, board)):
            return base * KEPT_HITS
        return base


KIT = Beryl()
