"""Rita: spend AP on other cards first so Time Paradox has Chronicle to convert, and fire Time Axis Collapse while the hand is full.

Chrono Archon turns spent AP into Chronicle, Time Paradox turns the Chronicle into Chronal Ascension for extra Rita AP, and Time Axis Collapse
gains damage for every Cost left in hand. The generic picker plays Time Paradox first, with no Chronicle yet, and plays Future Decreed as a skill.
"""

from src.en.kits.kit import PHASE_SETUP, Kit, base_name, owned

TIME_PARADOX = "Time Paradox"
# A random 3-Cost card is a gamble outside a hand built for it, so the plain card stays in hand. An Epiphany version is left to the generic picker.
FUTURE_DECREED = "Future Decreed"
# Cards played before Time Paradox has Chronicle from this turn's spending to convert.
PLAYED_FIRST = 2


class Rita(Kit):
    """Keeps Time Paradox for after the turn's first plays, Future Decreed for good, and fires Time Axis Collapse before the hand empties."""

    name = "Rita"
    cards = owned("Rita")
    # After Chrono Archon, so it counts the AP, and before the cards whose Cost it counts leave the hand.
    places = {"Time Axis Collapse": PHASE_SETUP + 0.5}

    def held(self, name, board):
        """Keep Time Paradox until cards have been played to build Chronicle, and the plain Future Decreed always.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        if name == FUTURE_DECREED:
            return True
        if base_name(name) != TIME_PARADOX or len(board.played) >= PLAYED_FIRST:
            return False
        # With nothing else left to play there is nothing to wait for.
        return any(base_name(other) != TIME_PARADOX and other != FUTURE_DECREED for other in board.hand)


KIT = Rita()
