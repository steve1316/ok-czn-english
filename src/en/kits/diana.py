"""Diana: discard With All My Heart! and Pistol of Purification instead of paying for them, and make Shakers first.

A Quietus card fires free when a card effect discards it, and Pistol of Purification re-triggers Resonance when discarded. The generic
picker pays an Action Point for both attacks as plain 100% hits, plays Milk & Pong last of all, and fires Liberated Feelings before it has bullets.
"""

from src.en.kits.kit import PHASE_FREE, Kit, base_name, owned

# Cards that discard from hand, so the cards below are better discarded than played.
OUTLETS = frozenset({"Blooming Love", "Heart Breaker"})
# Cards that do more discarded than paid for, held back while an outlet is in hand.
DISCARDABLE = frozenset({"With All My Heart!", "Pistol of Purification", "Cupid Shot"})
MILK_AND_PONG = "C\u2019mere, Milk & Pong!"
SHAKER = "Heart Shaker"
BREAKER = "Heart Breaker"
LIBERATED = "Liberated Feelings"


class Diana(Kit):
    """Holds the Quietus attacks for a discard, and orders Milk & Pong, the Shakers and Liberated Feelings."""

    name = "Diana"
    cards = owned("Diana")
    # Milk & Pong makes the Shakers, Liberated Feelings counts the bullets before they are played, then the Shakers, ahead of everything free.
    places = {MILK_AND_PONG: PHASE_FREE - 0.5, LIBERATED: PHASE_FREE - 0.25, SHAKER: PHASE_FREE - 0.1}

    def held(self, name, board):
        """Keep the discardable attacks while an outlet could discard them, and Liberated Feelings until it has two bullet types to count.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a card the kit would rather discard, or for a Liberated Feelings with too few bullets.
        """
        card = base_name(name)
        bases = {base_name(other) for other in board.hand}
        if card in DISCARDABLE:
            return bool(OUTLETS & bases)
        if card == LIBERATED:
            return not {SHAKER, BREAKER} <= bases
        return False


KIT = Diana()
