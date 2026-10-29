"""Renoa: stack Dirge Bullets in hand, then cash them in with Ballad, Instant Judgment and Last-Ditch Assault.

Every Dirge Bullet left in hand at turn end fires for free, and the payoff attacks gain damage for each one still in hand.
The generic picker plays the bullets like attacks and the payoffs on sight, so there is nothing left in hand for them to count.
"""

from src.en.game_battle import CARD_COST
from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, PHASE_SPENDS_EVERYTHING, Kit, base_name, count, owned

BULLET = "Dirge Bullet"
# The data gives no owner to the Finale bullet an Epiphany makes. Kept, it fires 160% x 2 at turn end, against 200% for a point on play.
BULLETS = frozenset({BULLET, "Dirge Bullet: Finale"})
# Discards up to two cards for a bullet each. A bullet fed to it fires its Extra Attack and comes back, per GameWith "add more Dirge Bullets".
FLOWER = "Flower of Devoured Fate"
LAST_DITCH = "Last-Ditch Assault"
# Bullets in hand before Last-Ditch Assault is worth its card, per im_Tsu ("5+ or even 9 bullets"). It has Retain, so waiting costs
# nothing while other cards can take the points. Live, the bullets were gone by the next turn, and two turns ended with points unspent.
LAST_DITCH_BULLETS = 5


def saving(board):
    """Say whether Last-Ditch Assault is in hand, so every extra bullet adds to it.

    Args:
        board: The `cards.Board` of the hand.

    Returns:
        True with Last-Ditch Assault in hand.
    """
    return count(board.hand, {LAST_DITCH}) > 0


class Renoa(Kit):
    """Never plays a bullet, saves Last-Ditch Assault for a full hand of them, and orders the generators and payoffs."""

    name = "Renoa"
    cards = owned("Renoa") | BULLETS
    # Echo of Sorrow makes a bullet first, then Ballad counts them, Instant Judgment spends one, and Last-Ditch spends them all.
    places = {
        "Echo of Sorrow": PHASE_PRIME,
        "Ballad of Pitch Black": PHASE_ATTACK,
        "Instant Judgment": PHASE_ATTACK + 0.25,
        LAST_DITCH: PHASE_ATTACK + 0.5,
        # Free, so generic play opened every turn with it and its discard took cards the points could still buy.
        FLOWER: PHASE_SPENDS_EVERYTHING + 1,
    }

    def phase(self, name, board, base):
        """Play Flower of Devoured Fate early while Last-Ditch Assault is in hand, for the bullets it makes to count.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The phase to sort by.
        """
        if base_name(name) == FLOWER and saving(board):
            return PHASE_PRIME
        return super().phase(name, board, base)

    def held(self, name, board):
        """Keep every bullet in hand to fire at turn end, and Last-Ditch Assault until enough of them are there or nothing else can be bought.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        card = base_name(name)
        if card in BULLETS:
            return True
        if card != LAST_DITCH or count(board.hand, BULLETS) >= LAST_DITCH_BULLETS:
            return False
        others = [base_name(other) for other in board.hand if base_name(other) not in BULLETS | {LAST_DITCH}]
        return any(0 <= CARD_COST.get(other, -1) <= board.action_points for other in others)

    def fodder(self, opener, name, board):
        """Feed Flower of Devoured Fate's discard the bullets first, which fire on the way and come back, unless Last-Ditch Assault wants more.

        Args:
            opener: The card whose play raised the prompt.
            name: A hand card the prompt could take.
            board: The `cards.Board` of the hand on offer.

        Returns:
            1 for a bullet while Last-Ditch Assault is not in hand, -1 for Last-Ditch Assault itself, else 0.
        """
        if base_name(opener) != FLOWER:
            return 0
        card = base_name(name)
        # Live, a discard offered two bullets and Last-Ditch Assault took a bullet, then the payoff.
        if card == LAST_DITCH:
            return -1
        return int(card in BULLETS and not saving(board))


KIT = Renoa()
