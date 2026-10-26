"""Haru: play Anchor Shot first, and keep her buffs and Anchor Pointer until there is a Shot for them to work on.

Anchor Shot grows with every use, Anchor Pointer moves it back to hand, and Lift Anchor and Charge Energy buff the cards in hand. The
generic picker plays all three free cards at the start of the turn, when Pointer finds a Shot already in hand and the buffs have no target.
"""

from src.en.game_battle import CARD_CATEGORY
from src.en.kits.kit import Kit, base_name, owned

SHOT = "Anchor Shot"
# Fetches Anchor Shot, which does nothing while one is already in hand.
POINTER = "Anchor Pointer"
# Buffs only the Anchor Shot in hand.
LIFT = "Lift Anchor"
# Buffs the attacks in hand.
CHARGE = "Charge Energy"
ATTACK_CATEGORY = "ATK"


class Haru(Kit):
    """Holds Anchor Pointer behind the Shot in hand, and the buffs until an attack is there to take them."""

    name = "Haru"
    cards = owned("Haru")

    def held(self, name, board):
        """Keep Anchor Pointer while a Shot is in hand, and Lift Anchor and Charge Energy while nothing is there to buff.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a card with nothing to act on.
        """
        card = base_name(name)
        bases = [base_name(other) for other in board.hand]
        if card == POINTER:
            return SHOT in bases
        if card == LIFT:
            return SHOT not in bases
        if card == CHARGE:
            return not any(CARD_CATEGORY.get(other) == ATTACK_CATEGORY and other in self.cards for other in bases)
        return False


KIT = Haru()
