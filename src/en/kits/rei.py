"""Rei: buff first, so the attacks that follow hit harder.

Strike of Darkness, Dark Condensation and Predator's Blade all raise the damage of attacks played after them for one turn.
The generic picker files the first and last as plain attacks and Dark Condensation as a skill, so they land after the hits they buff.
"""

from src.en.game_battle import CARD_CATEGORY
from src.en.kits.kit import ATTACK_CATEGORY, PHASE_PRIME, Kit, base_name, owned

CONDENSATION = "Dark Condensation"
# The X in Dark Condensation's "+X% Damage Amount" on the Attack its prompt picks.
CONDENSATION_BOOST = 1.5


class Rei(Kit):
    """Plays her three buffs ahead of the attacks, the basic-attack buff first and the team Morale last."""

    name = "Rei"
    cards = owned("Rei")
    # Strike of Darkness buffs basic attacks, Dark Condensation one chosen attack, and Predator's Blade gives the team Morale just before the hits.
    places = {"Strike of Darkness": PHASE_PRIME - 0.5, CONDENSATION: PHASE_PRIME, "Predator's Blade": PHASE_PRIME + 0.25}

    def worth(self, name, board, base, rate):
        """Price Dark Condensation by the Attack it would boost.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here each Attack in hand.

        Returns:
            The value to plan with.
        """
        if base_name(name) != CONDENSATION:
            return base
        # Live, its flat value tied with Photo Time's, so it lost the buy and Predator's Blade went unboosted.
        attacks = [rate(other) for other in board.hand if CARD_CATEGORY.get(base_name(other)) == ATTACK_CATEGORY]
        return base + CONDENSATION_BOOST * max(attacks, default=0)


KIT = Rei()
