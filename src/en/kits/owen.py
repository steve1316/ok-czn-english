"""Owen: spend Wind Charge's extra hit on his biggest attack, and Wind Riding to fetch it back.

Wind Charge adds a hit to the next Attack Owen plays, and Wind Riding returns a Wind Charge from the discard pile. The generic picker
prices Wind Charge's hit at a flat 100 and values Wind Riding as a plain shield.
"""

from src.en.kits.kit import PHASE_PRIME, Kit, base_name, count, owned

CHARGE = "Wind Charge"
RIDING = "Wind Riding"
# The Owen attacks a Wind Charge can land on, best first. Break Armor is a primer played ahead of it, so it never takes the hit.
TARGETS = ("Gale Strike", "Wind Slash", "Downward Cut")


def target(names):
    """Find the attack a Wind Charge would land on.

    Args:
        names: Canonical names of the cards in hand.

    Returns:
        The best Owen attack in hand, or None when there is none.
    """
    bases = {base_name(name) for name in names}
    return next((card for card in TARGETS if card in bases), None)


class Owen(Kit):
    """Prices Wind Charge and Wind Riding by the hit they bring.

    Wind Charge is never held back. Its hit waits for Owen's next attack, even on a later turn, so a spare point is not wasted on it.
    """

    name = "Owen"
    cards = owned("Owen")
    # After Break Armor, which shares its primer phase, so the hit lands on an attack that follows.
    places = {CHARGE: PHASE_PRIME + 0.5}

    def worth(self, name, board, base, rate):
        """Price Wind Charge as another hit of the attack it lands on, and Wind Riding as a Wind Charge back.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the attack's and Wind Charge's.

        Returns:
            The value to plan with.
        """
        card = base_name(name)
        if card == CHARGE and (aim := target(board.hand)):
            return rate(aim)
        # Only a Wind Charge from an earlier turn is in the discard pile for it to fetch, per im_Tsu and Adachi.
        if card == RIDING and count(board.last_turn, {CHARGE}):
            return base + rate(CHARGE)
        return base


KIT = Owen()
