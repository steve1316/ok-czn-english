"""Rita: spend AP on other cards first so Time Paradox has Chronicle to convert, and fire Time Axis Collapse while the hand is full.

Chrono Archon turns spent AP into Chronicle, Time Paradox turns the Chronicle into Chronal Ascension for extra Rita AP, and Time Axis Collapse
gains damage for every Cost left in hand. The generic picker plays Time Paradox first, with no Chronicle yet, plays Future Decreed as a skill,
and rates Chrono Archon as an unread card, below any attack.
"""

from src.en.game_battle import CARD_COST
from src.en.kits.kit import PHASE_SETUP, Kit, base_name, count, owned

TIME_PARADOX = "Time Paradox"
# The battle-long buff that turns spent AP into Chronicle, so nothing Time Paradox converts exists before it is out.
CHRONO_ARCHON = "Chrono Archon"
# A random 3-Cost card is a gamble outside a hand built for it, so the plain card stays in hand. An Epiphany version is left to the generic picker.
FUTURE_DECREED = "Future Decreed"
# Chrono Circle's creation, which deals its damage once for each point of its Cost. Playing one raises the Cost of the rest in hand by 1.
FATE_IMPRINT = "Fate Imprint"
# Cards played before Time Paradox has Chronicle from this turn's spending to convert.
PLAYED_FIRST = 2


def archon_waiting(board):
    """Say whether a Chrono Archon is in hand and none has been played this battle.

    Args:
        board: The `cards.Board` of the turn.

    Returns:
        True while the battle's Chronicle has yet to start.
    """
    return any(base_name(card) == CHRONO_ARCHON for card in board.hand) and not any(base_name(card) == CHRONO_ARCHON for card in board.battle)


class Rita(Kit):
    """Plays Chrono Archon first, keeps Time Paradox for after the turn's first plays, and Future Decreed for good."""

    name = "Rita"
    # Fate Imprint too, which the data gives no owner since Chrono Circle creates it.
    cards = owned("Rita") | {FATE_IMPRINT}
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
        if base_name(name) != TIME_PARADOX:
            return False
        if archon_waiting(board):
            return True
        if len(board.played) >= PLAYED_FIRST:
            return False
        # With nothing else left to play there is nothing to wait for.
        return any(base_name(other) != TIME_PARADOX and other != FUTURE_DECREED for other in board.hand)

    def worth(self, name, board, base, rate):
        """Price the battle's first Chrono Archon above every other card in hand, and Fate Imprint at its Cost this turn.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of the other cards in hand.

        Returns:
            The value to plan with.
        """
        if base_name(name) == FATE_IMPRINT:
            return base * (CARD_COST[FATE_IMPRINT] + count(board.played, {FATE_IMPRINT}))
        if base_name(name) != CHRONO_ARCHON or not archon_waiting(board):
            return base
        return max([base] + [rate(other) for other in board.hand if other != name]) + 1


KIT = Rita()
