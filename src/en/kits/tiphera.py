"""Tiphera: make Archetype cards after Dual Creation, and draw them only once a Quantum Seed has made some.

Quantum Seed creates Archetype cards, Dual Creation copies each pair as they are created, and Form Convergence draws Archetypes.
The generic picker plays Quantum Seed before Dual Creation, and Form Convergence on a deck that holds no Archetype to draw.
"""

from src.en.kits.kit import PHASE_FREE, Kit, base_name, owned

SEED = "Quantum Seed"
# The cards that draw Archetypes: Form Convergence, and the square one the Seed makes.
DRAWERS = frozenset({"Form Convergence", "Archetype: \u25a1"})


class Tiphera(Kit):
    """Plays Dual Creation ahead of Quantum Seed, and holds the cards that draw Archetypes until a Seed has been played."""

    name = "Tiphera"
    cards = owned("Tiphera")
    # Before the free Seed, so the pairs it creates are copied.
    places = {"Dual Creation": PHASE_FREE - 0.5}

    def held(self, name, board):
        """Keep the cards that draw Archetypes until a Quantum Seed was played this battle.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a card that would draw Archetypes while none were made.
        """
        if base_name(name) not in DRAWERS:
            return False
        return not any(base_name(played) == SEED for played in board.battle)


KIT = Tiphera()
