"""Chizuru: stack Oni Hunt and Tsukuyomi first, curse with Karmic Flames, and spend it all on one Shadow of the Moon last.

Oni Hunt and Tsukuyomi buffs build until a Shadow of the Moon uses them, and Shadow of the Moon+ is the bind-3 version of the card.
The generic picker plays Shadow at once as her best attack, and Tsukuyomi first, so the wisps land on whichever attack goes first.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

# Both spellings of the card, as the client shows it before and after its bind reaches three.
SHADOWS = frozenset({"Shadow of the Moon", "Shadow of the Moon+"})
ONI_HUNT = "Oni Hunt"
TSUKUYOMI = "Tsukuyomi"
# The buffs that wait for Shadow of the Moon, which are all played before it.
BUFFS = frozenset({ONI_HUNT, TSUKUYOMI})
# Last of every card, since it is the one hit all the buffs feed.
SHADOW_PHASE = PHASE_SPENDS_EVERYTHING - 0.5


class Chizuru(Kit):
    """Holds Shadow of the Moon until her buffs are played, then plays it last, with Tsukuyomi just ahead of Oni Hunt."""

    name = "Chizuru"
    cards = owned("Chizuru") | SHADOWS
    # Karmic Flames curses the target before the other hits, so it leads the attacks.
    places = {"Karmic Flames": PHASE_ATTACK - 0.5, **dict.fromkeys(SHADOWS, SHADOW_PHASE)}

    def held(self, name, board):
        """Keep Shadow of the Moon while a buff card is still in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Shadow of the Moon with buffs left to play.
        """
        return base_name(name) in SHADOWS and any(base_name(card) in BUFFS for card in board.hand)

    def phase(self, name, board, base):
        """Put Tsukuyomi right before Oni Hunt, so the wisps count its hits.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == TSUKUYOMI and any(base_name(card) == ONI_HUNT for card in board.hand):
            return PHASE_PRIME - 0.5
        return super().phase(name, board, base)


KIT = Chizuru()
