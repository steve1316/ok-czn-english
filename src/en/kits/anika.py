"""Anika: discount one big attack with Warming Up, spend Rampage Trigger last, and end the turn with Reloading.

Warming Up cuts the cost of only the next Anika card, and Reloading is a Finale that draws Lead cards for next turn and ends this one.
The generic picker plays the free Reloading first, Warming Up with no big attack to discount, and Rampage Trigger as a plain 100% hit.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

RELOADING = "Reloading"
WARMING = "Warming Up"
IGNITION = "Ignition Slash"
RAMPAGE = "Rampage Trigger"
# The two-cost attacks a Warming Up discount is worth taking on.
BIG_ATTACKS = (IGNITION, RAMPAGE)
# Hits Rampage Trigger lands, which its 100% line does not show (Game8, gamesaiyan).
RAMPAGE_HITS = 4


class Anika(Kit):
    """Plays Warming Up just ahead of her big attack, Rampage Trigger last of the attacks, and Reloading last of all."""

    name = "Anika"
    cards = owned("Anika")
    # Ignition Slash leads the attacks since it breaks Tenacity, and Rampage Trigger follows them all.
    places = {IGNITION: PHASE_ATTACK - 0.25, RAMPAGE: PHASE_ATTACK + 0.5, RELOADING: PHASE_SPENDS_EVERYTHING + 1}

    def held(self, name, board):
        """Keep Warming Up while no two-cost attack is in hand to take its discount.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Warming Up with nothing to discount.
        """
        return base_name(name) == WARMING and not any(base_name(card) in BIG_ATTACKS for card in board.hand)

    def phase(self, name, board, base):
        """Put Warming Up right before the first big attack.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == WARMING:
            # Ignition Slash leads when it is in hand, else the discount waits for Rampage Trigger.
            slash = any(base_name(card) == IGNITION for card in board.hand)
            return PHASE_ATTACK - 0.5 if slash else PHASE_ATTACK + 0.25
        return super().phase(name, board, base)

    def worth(self, name, board, base, rate):
        """Price Rampage Trigger for all its hits.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it, one hit's damage.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return base * RAMPAGE_HITS if base_name(name) == RAMPAGE else base


KIT = Anika()
