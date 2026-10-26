"""Nine: level Hew with exhausts, then fire it once at its top level.

Each time Hew is exhausted it becomes the next level in hand, and the last level is the payoff. Fighting Spirit and Fatal Strike exhaust it
and Experienced Strike boosts exhaust cards. The generic picker plays a low Hew for its 3 AP on sight and leaves Fighting Spirit as filler.
"""

import re

from src.en.kits.kit import PHASE_PRIME, Kit, base_name, owned

# A Hew as the client writes it: "Hew", "Hew Lv. 2" or "Hew (Extreme) Lv. 5".
HEW = re.compile(r"^Hew(?: \((?P<variant>[^)]+)\))?(?: Lv\. (?P<level>\d+))?$")
# Hew versions with their own rules, which the kit leaves to the generic picker.
OWN_RULES = frozenset({"Flash", "Ambush"})
# The level at which Hew is fully grown, and the one Extreme grows to.
TOP_LEVEL = 3
EXTREME_TOP_LEVEL = 5
FIGHTING_SPIRIT = "Fighting Spirit"
FATAL_STRIKE = "Fatal Strike"
EXPERIENCED_STRIKE = "Experienced Strike"


def stage(name):
    """Say how grown a Hew is.

    Args:
        name: A canonical card name from the hand or from what the turn has played.

    Returns:
        "low" for a Hew below its top level, "max" for one at it, or None for any other card and for a Hew with its own rules.
    """
    found = HEW.match(name)
    if not found or found.group("variant") in OWN_RULES:
        return None
    top = EXTREME_TOP_LEVEL if found.group("variant") == "Extreme" else TOP_LEVEL
    return "max" if int(found.group("level") or 0) >= top else "low"


class Nine(Kit):
    """Holds Hew until it is fully grown, and spends the exhaust cards on growing it or firing it."""

    name = "Nine"
    cards = owned("Nine")

    def claims(self, name):
        """Say whether a card switches this kit on, counting every level of Hew.

        Args:
            name: A canonical card name from the hand.

        Returns:
            True for any Hew or one of his other cards.
        """
        return bool(HEW.match(name)) or super().claims(name)

    def held(self, name, board):
        """Keep Hew until it is fully grown, and keep the exhaust cards that would only waste it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep the card in hand.
        """
        hand = [base_name(card) for card in board.hand]
        grown = stage(name)
        if grown == "low":
            return True
        if grown == "max":
            # Fighting Spirit fires a full Hew for one point instead of two.
            return FIGHTING_SPIRIT in hand
        card = base_name(name)
        if card == FATAL_STRIKE:
            # It would exhaust a full Hew and lose it for the turn.
            return any(stage(other) == "max" for other in board.hand)
        if card == FIGHTING_SPIRIT:
            # Once Hew is played the next one only comes next turn, so there is nothing left to fire.
            return not any(stage(other) for other in board.hand) and any(HEW.match(other) for other in board.played)
        return False

    def worth(self, name, board, base, rate):
        """Price the exhaust cards by the Hew they level or fire.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the Hew's.

        Returns:
            The value to plan with.
        """
        if base_name(name) in (FIGHTING_SPIRIT, FATAL_STRIKE):
            return max([base, *(rate(other) for other in board.hand if stage(other))])
        return base

    def phase(self, name, board, base):
        """Play Experienced Strike ahead of the Hew or exhaust it boosts.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if base_name(name) == EXPERIENCED_STRIKE and any(stage(other) for other in board.hand):
            return PHASE_PRIME
        return base


KIT = Nine()
