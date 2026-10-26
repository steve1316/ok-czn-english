"""Owen: spend Wind Charge's extra hit on his biggest attack, and Wind Riding to fetch it back.

Wind Charge adds a hit to the next Attack Owen plays, and Wind Riding returns a Wind Charge from the discard pile. The generic picker
plays Wind Charge with no Owen attack to follow, prices its hit at a flat 100, and values Wind Riding as a plain shield.
"""

from src.en.kits.kit import PHASE_PRIME, Kit, base_name, owned

CHARGE = "Wind Charge"
RIDING = "Wind Riding"
# The Owen attacks a Wind Charge can land on, best first. Break Armor is a primer played ahead of it, so it never takes the hit.
TARGETS = ("Gale Strike", "Wind Slash", "Downward Cut")
# Wind Charge plus the attack after it.
CHARGE_AND_ATTACK = 2


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
    """Keeps Wind Charge for an attack it can land on, and prices it and Wind Riding by the hit they bring."""

    name = "Owen"
    cards = owned("Owen")
    # After Break Armor, which shares its primer phase, so the hit lands on an attack that follows.
    places = {CHARGE: PHASE_PRIME + 0.5}

    def held(self, name, board):
        """Keep Wind Charge while no Owen attack, or no point to play one, would follow it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Wind Charge with nothing to land on.
        """
        return base_name(name) == CHARGE and (target(board.hand) is None or board.action_points < CHARGE_AND_ATTACK)

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
        if card == RIDING and any(base_name(played) == CHARGE for played in board.last_turn):
            return base + rate(CHARGE)
        return base


KIT = Owen()
