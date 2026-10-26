"""Nia: line up her draw and discard cards in the order they feed each other.

Adagio puts a discard on top of the draw pile for G Chord to play, and Soul Riff only counts discards made after it.
The generic picker plays G Chord, Soul Riff and Curiosity after the attacks, and Mute Accent whenever points are spare.
"""

from src.en.game_battle import CARD_COST
from src.en.kits.kit import PHASE_FREE, PHASE_OTHER, PHASE_SETUP, Kit, base_name, owned

MUTE_ACCENT = "Mute Accent"


class Nia(Kit):
    """Orders the cycling cards, and keeps Mute Accent from discarding a card the hand still wants."""

    name = "Nia"
    cards = owned("Nia")
    # Soul Riff before the discarders, Adagio at `PHASE_FREE`, then G Chord to play what Adagio left on top, then Curiosity, and Mute Accent last.
    places = {
        "Soul Riff": PHASE_FREE - 0.5,
        "G Chord": PHASE_SETUP,
        "Nia\u2019s Curiosity": PHASE_SETUP + 0.5,
        MUTE_ACCENT: PHASE_OTHER + 0.5,
    }

    def held(self, name, board):
        """Keep Mute Accent while a dearer card is in hand, since it discards the highest cost one.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Mute Accent that would throw away a dearer card.
        """
        if base_name(name) != MUTE_ACCENT:
            return False
        return any(CARD_COST.get(base_name(other), 0) > CARD_COST[MUTE_ACCENT] for other in board.hand)


KIT = Nia()
