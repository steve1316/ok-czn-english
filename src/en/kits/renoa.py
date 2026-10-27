"""Renoa: stack Dirge Bullets in hand, then cash them in with Ballad, Instant Judgment and Last-Ditch Assault.

Every Dirge Bullet left in hand at turn end fires for free, and the payoff attacks gain damage for each one still in hand.
The generic picker plays the bullets like attacks and the payoffs on sight, so there is nothing left in hand for them to count.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, Kit, base_name, owned

BULLET = "Dirge Bullet"
LAST_DITCH = "Last-Ditch Assault"
# Bullets in hand before Last-Ditch Assault is worth its card, per im_Tsu ("5+ or even 9 bullets"). It has Retain, so waiting is free.
LAST_DITCH_BULLETS = 5


class Renoa(Kit):
    """Never plays a bullet, saves Last-Ditch Assault for a full hand of them, and orders the generators and payoffs."""

    name = "Renoa"
    cards = owned("Renoa") | {BULLET}
    # Echo of Sorrow makes a bullet first, then Ballad counts them, Instant Judgment spends one, and Last-Ditch spends them all.
    places = {
        "Echo of Sorrow": PHASE_PRIME,
        "Ballad of Pitch Black": PHASE_ATTACK,
        "Instant Judgment": PHASE_ATTACK + 0.25,
        LAST_DITCH: PHASE_ATTACK + 0.5,
    }

    def held(self, name, board):
        """Keep every bullet in hand to fire at turn end, and Last-Ditch Assault until enough of them are there.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        card = base_name(name)
        if card == BULLET:
            return True
        return card == LAST_DITCH and sum(base_name(other) == BULLET for other in board.hand) < LAST_DITCH_BULLETS


KIT = Renoa()
