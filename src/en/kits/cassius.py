"""Cassius: draw and shuffle with the real deck cards, play Triple 0 after the attacks, and keep Shuffle as a rescue.

Triple 0 is a free Quest card that gains damage for every attack card played this turn, and Shuffle throws the whole hand away to redraw it.
The generic picker plays Triple 0 first, buys his filler (Wild Card, Cards, Mana Field) before Pop Eyed Popper and Joker, and shuffles at once.
"""

from src.en.game_battle import CARD_CATEGORY
from src.en.kits.kit import PHASE_OTHER, Kit, base_name, owned

TRIPLE_ZERO = "Triple 0"
SHUFFLE = "Shuffle"
# Every source says to cut these, so they only take Action Points nothing else wants.
FILLER = frozenset({"Cards", "Wild Card", "Mana Field"})
# Categories of the cards that are not worth playing, which do not count as something else to play before Shuffle.
DEAD_CATEGORIES = frozenset({"CURSE", "ABNORM"})


class Cassius(Kit):
    """Ranks his filler last, plays Triple 0 after the attacks that raise it, and holds Shuffle while other cards can be played."""

    name = "Cassius"
    # Triple 0 is a Quest card, so it has no owner and is named here.
    cards = owned("Cassius") | {TRIPLE_ZERO}
    # After every attack, since it gains damage for each one played, and still before the late skills.
    places = {TRIPLE_ZERO: PHASE_OTHER - 0.5}

    def held(self, name, board):
        """Keep Shuffle while any other playable card is in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Shuffle with something else to play first.
        """
        if base_name(name) != SHUFFLE:
            return False
        return any(base_name(card) != SHUFFLE and CARD_CATEGORY.get(base_name(card)) not in DEAD_CATEGORIES for card in board.hand)

    def worth(self, name, board, base, rate):
        """Spend his filler cards only on points no other card wants.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return 0 if base_name(name) in FILLER else base


KIT = Cassius()
