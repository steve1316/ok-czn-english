"""Amir: build Metalization first, spend it with Full Metal Hurricane, and keep Iron Skin for last.

Hovering Metal and Metal Extraction give Metalization, each Shield she gains then spends a stack on a hit, and Iron Skin is a Finale ending the turn.
The generic picker plays the generators and Iron Skin in value order after the attacks, and rates Steel Barrier below Rapier.
"""

from src.en.kits.kit import PHASE_SETUP, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

# The cards that give Metalization stacks, so they go ahead of anything that shields or spends.
GENERATORS = frozenset({"Hovering Metal", "Metal Extraction"})
IRON_SKIN = "Iron Skin"
FMH = "Full Metal Hurricane"
BARRIER = "Steel Barrier"
# Damage of the hit a Shield sets off once Full Metal Hurricane is up, from the 80% defense-based hit in the research.
SHIELD_HIT = 80


class Amir(Kit):
    """Puts the generators first and Iron Skin last, and prices Steel Barrier by the hit Full Metal Hurricane gives it."""

    name = "Amir"
    cards = owned("Amir")
    # Iron Skin is a Finale that ends the turn on play, so it sits past every other phase.
    places = {**dict.fromkeys(GENERATORS, PHASE_SETUP), IRON_SKIN: PHASE_SPENDS_EVERYTHING + 1}

    def worth(self, name, board, base, rate):
        """Price Steel Barrier as a shield plus the hit it sets off once Full Metal Hurricane has been played this turn.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        if base_name(name) == BARRIER and any(base_name(played) == FMH for played in board.played):
            return base + SHIELD_HIT
        return base


KIT = Amir()
