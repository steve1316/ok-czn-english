"""Renoa: stack Dirge Bullets in hand, then cash them in with Ballad, Instant Judgment and Last-Ditch Assault.

Every Dirge Bullet left in hand at turn end fires for free, and the payoff attacks gain damage for each one still in hand.
The generic picker plays the bullets like attacks and the payoffs on sight, so there is nothing left in hand for them to count.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

BULLET = "Dirge Bullet"
# The data gives no owner to the Finale bullet an Epiphany makes. Kept, it fires 160% x 2 at turn end, against 200% for a point on play.
BULLETS = frozenset({BULLET, "Dirge Bullet: Finale"})
# Discards up to two cards for a bullet each. A bullet fed to it fires its Extra Attack and comes back, per GameWith "add more Dirge Bullets".
FLOWER = "Flower of Devoured Fate"
LAST_DITCH = "Last-Ditch Assault"
# Bullets in hand before Last-Ditch Assault is worth its card, per im_Tsu ("5+ or even 9 bullets"). It has Retain, so waiting is free.
LAST_DITCH_BULLETS = 5


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

    def held(self, name, board):
        """Keep every bullet in hand to fire at turn end, and Last-Ditch Assault until enough of them are there.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        card = base_name(name)
        if card in BULLETS:
            return True
        return card == LAST_DITCH and sum(base_name(other) in BULLETS for other in board.hand) < LAST_DITCH_BULLETS

    def fodder(self, opener, name):
        """Feed Flower of Devoured Fate's discard the bullets first, which fire on the way and come back.

        Args:
            opener: The card whose play raised the prompt.
            name: A hand card the prompt could take.

        Returns:
            True for a bullet under Flower of Devoured Fate's discard.
        """
        return base_name(opener) == FLOWER and base_name(name) in BULLETS


KIT = Renoa()
