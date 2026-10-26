"""The shape every kit takes, and the name a card has before its Epiphany."""

import re

# The Epiphany a card has been upgraded with, which the client writes as a suffix: "Shard:Light (Cycle)".
EPIPHANY_SUFFIX = re.compile(r"\s*\([^)]*\)$")

# Where a card sits in a turn, lowest first. Here rather than in cards.py so a kit can place a card between two of them.
PHASE_ESCAPE = 0
PHASE_EPIPHANY = 1
PHASE_FREE = 2
PHASE_SETUP = 3
PHASE_PRIME = 4
PHASE_ATTACK = 5
PHASE_OTHER = 6
PHASE_SPENDS_EVERYTHING = 7


def base_name(name):
    """Drop the Epiphany from a card name.

    Args:
        name: A card name, maybe upgraded.

    Returns:
        The name the card has before any Epiphany.
    """
    return EPIPHANY_SUFFIX.sub("", name)


class Kit:
    """One playstyle. Every hook does nothing unless a subclass overrides it, so a kit only says what it changes.

    Hooks get the `cards.Board`, whose `hand` holds canonical names left to right. A kit never imports `cards.py`, which imports this.
    """

    # Who the kit plays, for the log.
    name = ""
    # Base names of the cards that switch the kit on while one is in hand.
    cards = frozenset()

    def claims(self, name):
        """Say whether a card switches this kit on.

        Args:
            name: A canonical card name from the hand.

        Returns:
            True when the card, without its Epiphany, is one of the kit's.
        """
        return base_name(name) in self.cards

    def reading(self, hand, count):
        """Correct the hand reading where the kit knows a card's place better than OCR does.

        Args:
            hand: Hand cards as `_hand_cards` reads them, with canonical names.
            count: The hand size the hand counter reads.

        Returns:
            The hand, corrected or as it was.
        """
        return hand

    def held(self, name, board):
        """Say whether a card must stay in hand, neither played nor given up to a prompt.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep it.
        """
        return False

    def worth(self, name, board, base, rate):
        """Adjust what a card is worth to the turn.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, for a kit that prices one card against another.

        Returns:
            The value to plan with.
        """
        return base

    def phase(self, name, board):
        """Place a card in the turn where the generic order puts it wrong.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.

        Returns:
            A `PHASE_` value, or a number between two of them, or None to leave the card where the generic order puts it.
        """
        return None

    def waiting(self, names, count):
        """Say whether the turn should sit for a frame rather than play or end.

        Args:
            names: Every card the hand reads as.
            count: The hand size the hand counter reads.

        Returns:
            True while the game is still about to change the hand by itself.
        """
        return False
