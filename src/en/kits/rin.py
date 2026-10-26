"""Rin: take Dark Mist Stance first, buff, then attack, and keep the allies' attacks for last.

Her attacks and Inner Art gain from the stance, Black Dance gains a hit per Skill card in hand, and any ally attack played ends the stance.
The generic picker plays Drawing Slash before Destruction, Inner Art after the attacks, Protection ahead of Black Dance, and ally attacks anywhere.
"""

from src.en.game_battle import CARD_CATEGORY, CARD_OWNER
from src.en.kits.kit import PHASE_ATTACK, PHASE_FREE, PHASE_PRIME, Kit, base_name, owned

# Black Dance gains a hit per Skill card in hand, so the shield skill stays in hand while it does.
BLACK_DANCE = "Dark Mist Secret Art: Black Dance"
PROTECTION = "Protection"
ATTACK_CATEGORY = "ATK"


class Rin(Kit):
    """Opens the stance with Destruction, buffs before attacking, and plays other combatants' attacks after her own."""

    name = "Rin"
    cards = owned("Rin")
    # Destruction gives the stance before Drawing Slash, whose bonus only counts in it, and Inner Art goes after both and before the attacks.
    places = {"Dark Mist Secret Art: Destruction": PHASE_FREE - 0.5, "Dark Mist Inner Art": PHASE_PRIME}

    def held(self, name, board):
        """Keep Protection in hand while Black Dance is there to count it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Protection played ahead of a Black Dance.
        """
        return base_name(name) == PROTECTION and any(base_name(other) == BLACK_DANCE for other in board.hand)

    def phase(self, name, board, base):
        """Play other combatants' attacks after all of Rin's, since each one ends the stance.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        card = base_name(name)
        if base == PHASE_ATTACK and CARD_CATEGORY.get(card) == ATTACK_CATEGORY and CARD_OWNER.get(card) not in (None, self.name):
            return PHASE_ATTACK + 0.75
        return super().phase(name, board, base)


KIT = Rin()
