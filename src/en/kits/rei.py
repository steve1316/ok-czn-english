"""Rei: buff first, so the attacks that follow hit harder.

Strike of Darkness, Dark Condensation and Predator's Blade all raise the damage of attacks played after them for one turn.
The generic picker files the first and last as plain attacks and Dark Condensation as a skill, so they land after the hits they buff.
"""

from src.en.game_battle import CARD_CATEGORY, CARD_OWNER
from src.en.game_quality import CARD_RARITY
from src.en.kits.kit import ATTACK_CATEGORY, PHASE_PRIME, Kit, base_name, owned

CONDENSATION = "Dark Condensation"
# The X in Dark Condensation's "+X% Damage Amount" on the Attack its prompt picks.
CONDENSATION_BOOST = 1.5
STRIKE = "Strike of Darkness"
# The +X% Damage Amount Strike of Darkness gives Basic Attack cards for the turn, +150% upgraded (GameWith).
STRIKE_BOOST = 1.0
# A combatant's own Common cards are their basics, so a Common Attack with an owner is a Basic Attack card.
BASIC_RARITY = "COMMON"


def basic_attack(card):
    """Say whether a card is a Basic Attack card, which Strike of Darkness boosts.

    Args:
        card: A card's base name.

    Returns:
        True for a combatant's own Common Attack.
    """
    return CARD_RARITY.get(card) == BASIC_RARITY and card in CARD_OWNER and CARD_CATEGORY.get(card) == ATTACK_CATEGORY


class Rei(Kit):
    """Plays her three buffs ahead of the attacks, the basic-attack buff first and the team Morale last."""

    name = "Rei"
    cards = owned("Rei")
    # Strike of Darkness buffs basic attacks, Dark Condensation one chosen attack, and Predator's Blade gives the team Morale just before the hits.
    places = {STRIKE: PHASE_PRIME - 0.5, CONDENSATION: PHASE_PRIME, "Predator's Blade": PHASE_PRIME + 0.25}

    def worth(self, name, board, base, rate):
        """Price Dark Condensation by the Attack it would boost, and Strike of Darkness by the Basic Attack it would.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here each Attack in hand.

        Returns:
            The value to plan with.
        """
        card = base_name(name)
        if card == CONDENSATION:
            # Live, its flat value tied with Photo Time's, so it lost the buy and Predator's Blade went unboosted.
            attacks = [rate(other) for other in board.hand if CARD_CATEGORY.get(base_name(other)) == ATTACK_CATEGORY]
            return base + CONDENSATION_BOOST * max(attacks, default=0)
        if card == STRIKE:
            # Live, it tied with Dark Blade, and two unboosted Dark Blades took the turn's last two points.
            basics = [rate(other) for other in board.hand if basic_attack(base_name(other))]
            return base + STRIKE_BOOST * max(basics, default=0)
        return base


KIT = Rei()
