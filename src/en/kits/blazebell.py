"""Blazebell: stack Blue Flame into Fluttering Embers instead of playing it, and buff and Melt ahead of the attacks.

Blue Flame copies Bind into one card that turns into a free Fluttering Embers at four, and each stack heals by itself. The generic picker
spends leftover points on Blue Flame even at full HP, which resets the stack, and plays Vestige of Flames and Flametouch after other attacks.
"""

import re

from src.en.game_battle import CARD_CATEGORY, CARD_COST, CARD_OWNER, COMBATANT_ATTRIBUTE
from src.en.kits.kit import ATTACK_CATEGORY, PHASE_ATTACK, PHASE_OTHER, PHASE_PRIME, Kit, base_name, owned, text

BLUE_FLAME = "Blue Flame"
EMBERS = "Fluttering Embers"
VESTIGE = "Vestige of Flames"
# Blue Flame stacks this many times before it turns into Fluttering Embers, from its "Bind (1/4)" tag.
BIND_MAX = 4
# The share of HP left after the next hit below which one Blue Flame's heal is worth more than its stack. Matches `ego.GUARD_BELOW`.
LOW_HEALTH = 0.3
# How many Blue Flame a card's text makes, as in "Create 2 Blue Flame".
CREATES_FLAMES = re.compile(r"\bCreate (\d+) Blue Flame")
OWN_ATTRIBUTE = COMBATANT_ATTRIBUTE["Blazebell"]


def other_attribute(name):
    """Say whether a card belongs to a combatant of another attribute, which turns off Fluttering Embers' Purity draw.

    Args:
        name: A canonical card name from the hand.

    Returns:
        True for another attribute's card. A card with no owner has no attribute, so it never counts.
    """
    attribute = COMBATANT_ATTRIBUTE.get(CARD_OWNER.get(base_name(name), ""))
    return attribute is not None and attribute != OWN_ATTRIBUTE


class Blazebell(Kit):
    """Holds Blue Flame, plays Vestige and Flametouch before the attacks, and Fluttering Embers after other attributes' cards."""

    name = "Blazebell"
    cards = owned("Blazebell")
    # Melting raises the Justice damage the target takes for the turn, so it leads the attacks.
    places = {VESTIGE: PHASE_PRIME, "Flametouch": PHASE_ATTACK - 0.5}

    def held(self, name, board):
        """Keep Blue Flame for its stack unless the team is about to drop, and Vestige until the turn can also pay for an attack.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Blue Flame on a team that is not in danger, or a Vestige with no attack it can buff.
        """
        card = base_name(name)
        if card == BLUE_FLAME:
            return board.health is None or board.health >= LOW_HEALTH
        if card == VESTIGE:
            # Vestige Retains, so a turn with no attack to buff loses nothing by keeping it.
            spare = board.action_points - CARD_COST[VESTIGE]
            return not any(CARD_CATEGORY.get(base_name(other)) == ATTACK_CATEGORY and CARD_COST.get(base_name(other), 0) <= spare
                           for other in board.hand)
        return False

    def worth(self, name, board, base, rate):
        """Count each Blue Flame a card makes as a quarter of the Fluttering Embers four of them turn into.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here Fluttering Embers'.

        Returns:
            The value to plan with.
        """
        made = sum(int(found) for found in CREATES_FLAMES.findall(text(name, board)))
        return base + made * rate(EMBERS) / BIND_MAX if made else base

    def phase(self, name, board, base):
        """Play Fluttering Embers after every card of another attribute, so its Purity draw fires.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == EMBERS and any(other_attribute(other) for other in board.hand):
            return PHASE_OTHER + 0.5
        return super().phase(name, board, base)


KIT = Blazebell()
