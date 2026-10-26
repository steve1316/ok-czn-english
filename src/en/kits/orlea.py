"""Orlea: grow retained creatures, and keep the cards that need creatures in hand until they have some.

Swiftie, Softie and Sturdie keep their place in hand and grow, Will of Light retains everything and Growth Acceleration retains one card twice.
The generic picker plays Growing Creature and the retain cards on sight, and plays Swiftie before the Softie that buffs it.
"""

from src.en.kits.kit import PHASE_FREE, Kit, base_name, owned

# Name stems of the creatures her cards make, which the client writes with stars: "Swiftie" followed by a star count.
SWIFTIE = "Swiftie"
SOFTIE = "Softie"
STURDIE = "Sturdie"
CREATURES = (SWIFTIE, SOFTIE, STURDIE)
GROWING_CREATURE = "Growing Creature"
WILL_OF_LIGHT = "Will of Light"
GROWTH_ACCELERATION = "Growth Acceleration"
# Retained cards Will of Light needs in hand to be worth a point.
FULL_HAND = 3


def retained(names):
    """Count the cards in hand that Retain keeps and grows.

    Args:
        names: Canonical names of the cards in hand.

    Returns:
        How many are creatures or a Growing Creature.
    """
    return sum(name.startswith(CREATURES) or base_name(name) == GROWING_CREATURE for name in names)


class Orlea(Kit):
    """Keeps Growing Creature for good, and Will of Light and Growth Acceleration for a hand of creatures, and buffs with Softie first."""

    name = "Orlea"
    cards = owned("Orlea")

    def claims(self, name):
        """Say whether a card switches this kit on, counting every creature.

        Args:
            name: A canonical card name from the hand.

        Returns:
            True for any creature or one of her other cards.
        """
        return name.startswith(CREATURES) or super().claims(name)

    def held(self, name, board):
        """Keep the cards that waste a point without creatures in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        card = base_name(name)
        if card == GROWING_CREATURE:
            # Played it makes a one-star creature, and kept it becomes a three-star one at the next turn.
            return True
        if card == WILL_OF_LIGHT:
            return retained(board.hand) < FULL_HAND
        if card == GROWTH_ACCELERATION:
            return not retained(board.hand)
        return False

    def phase(self, name, board, base):
        """Play Softie ahead of Swiftie, so the team buff is up for the attack.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        return PHASE_FREE - 0.5 if name.startswith(SOFTIE) else base


KIT = Orlea()
