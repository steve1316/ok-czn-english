"""Rin: take Dark Mist Stance before the cards that pay off in it, and keep the allies' attacks for last.

The stance is gained by a card whose text says so and lost to any other combatant's attack. Inner Art carries it into the next turn.
The generic picker knows none of this, so it plays Black Dance before the stance is up and spends the Skill cards Black Dance counts.
"""

import re

from src.en.game_battle import CARD_CATEGORY
from src.en.kits.kit import ATTACK_CATEGORY, PHASE_ATTACK, PHASE_FREE, PHASE_PRIME, SKILL_CATEGORY, Kit, base_name, borrowed, count, owned, text

BLACK_DANCE = "Dark Mist Secret Art: Black Dance"
INNER_ART = "Dark Mist Inner Art"
# Cards whose text the data writes without the "Dark Mist Stance:" condition the client shows, so only their names mark them.
# Black Dance adds a hit per Skill card in hand, Drawing Slash and Inner Art raise Damage Amount, and Annihilation can cut Rin's costs.
PAYOFFS = frozenset({BLACK_DANCE, INNER_ART, "Drawing Slash", "Dark Mist Secret Art: Annihilation"})
# A played card that takes the stance, which an Epiphany can drop: one Destruction moves cards instead.
GAINS = re.compile(r"^Gain Dark Mist Stance", re.M)
# An Annihilation whose Epiphany cuts the cost of Rin's other cards, so it goes before them.
COST_CUT = "Decrease Cost of all cards of this unit"


class Rin(Kit):
    """Plays a stance card before the payoffs, Black Dance before the Skill cards it counts, and other combatants' attacks after her own."""

    name = "Rin"
    cards = owned("Rin")
    # Destruction gives the stance before Drawing Slash, whose bonus only counts in it, and Inner Art goes after both and before the attacks.
    places = {"Dark Mist Secret Art: Destruction": PHASE_FREE - 0.5, INNER_ART: PHASE_PRIME}

    def gains(self, name, board):
        """Say whether playing a card takes the stance.

        Args:
            name: A canonical card name.
            board: The `cards.Board`, for the version of the card the deck holds.

        Returns:
            True when the card's text gains Dark Mist Stance.
        """
        return bool(GAINS.search(text(name, board)))

    def in_stance(self, board):
        """Follow the stance through what this turn has played.

        Args:
            board: The `cards.Board`, whose `played` and `last_turn` hold the turn's cards and the one before.

        Returns:
            True while the stance is up.
        """
        up = bool(count(board.last_turn, {INNER_ART}))
        for card in board.played:
            if self.gains(card, board):
                up = True
            elif borrowed(base_name(card), ATTACK_CATEGORY, self.name):
                up = False
        return up

    def stance_coming(self, board):
        """Say whether the stance is up or a card in hand can take it.

        Args:
            board: The `cards.Board` the turn is planned against.

        Returns:
            True when the payoffs will have the stance to work in.
        """
        return self.in_stance(board) or any(self.gains(card, board) for card in board.hand)

    def counted(self, name, board):
        """Say whether a card is a Skill that Black Dance counts while it stays in hand.

        Args:
            name: A canonical card name.
            board: The `cards.Board`, for the version of the card the deck holds.

        Returns:
            True for a Skill that neither takes the stance nor is Inner Art, both of which go first.
        """
        return CARD_CATEGORY.get(base_name(name)) == SKILL_CATEGORY and base_name(name) != INNER_ART and not self.gains(name, board)

    def worth(self, name, board, base, rate):
        """Rate Black Dance by the hits the Skill cards in hand add, which go to the card taking the stance while it is down.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, for Black Dance's one hit.

        Returns:
            The value to plan with.
        """
        if not count(board.hand, {BLACK_DANCE}):
            return base
        hits = sum(self.counted(card, board) for card in board.hand)
        if base_name(name) == BLACK_DANCE:
            return base * (1 + hits) if self.in_stance(board) else base
        if not self.in_stance(board) and self.gains(name, board):
            return base + rate(BLACK_DANCE) * hits
        return base

    def phase(self, name, board, base):
        """Place the stance cards first, then the payoffs, then the Skills Black Dance counts, and other combatants' attacks last.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        card = base_name(name)
        coming = self.stance_coming(board)
        if not self.in_stance(board) and card not in PAYOFFS and self.gains(name, board) and count(board.hand, PAYOFFS):
            return PHASE_FREE - 0.5
        if card == "Dark Mist Secret Art: Annihilation" and coming and COST_CUT in text(name, board):
            return PHASE_FREE + 0.5
        if coming and count(board.hand, {BLACK_DANCE}) and card != BLACK_DANCE and self.counted(name, board):
            return PHASE_ATTACK + 0.5
        if base == PHASE_ATTACK and borrowed(card, ATTACK_CATEGORY, self.name):
            return PHASE_ATTACK + 0.75
        return super().phase(name, board, base)


KIT = Rin()
