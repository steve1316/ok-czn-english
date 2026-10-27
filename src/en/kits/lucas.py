"""Lucas: play S.S.S before the Launcher Bullets it buffs.

S.S.S gives "+X% Bullet card Damage" for one turn, and its Epiphanies add damage per bullet in hand or to the next bullet.
The generic picker ranks it as a plain 100% attack, so it often lands after the bullets it was meant to raise.
"""

from src.en.kits.kit import PHASE_PRIME, Kit, owned

SSS = "S.S.S"


class Lucas(Kit):
    """Plays S.S.S ahead of every bullet and attack."""

    name = "Lucas"
    cards = owned("Lucas")
    # With the primers, ahead of the bullets and attacks it buffs.
    places = {SSS: PHASE_PRIME}


KIT = Lucas()
