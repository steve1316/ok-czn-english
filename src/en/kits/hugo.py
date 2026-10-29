"""Hugo: build Commence the Hunt stacks with skills, then spend them with attacks.

Dingo Howling and Fan of Daggers give stacks, Hunting Instincts gives one for each Skill another combatant plays, and stacks carry over
between turns. The generic picker plays Dingo Howling after the attacks that spend it, and Quick Fix first for a draw that needs a stack.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_OTHER, PHASE_PRIME, SKILL_CATEGORY, Kit, base_name, borrowed, count, owned

# His cards that give Commence the Hunt stacks.
STACKERS = frozenset({"Dingo Howling", "Fan of Daggers"})
# Draws only in a Commence the Hunt state, so without a recent stack-giver it waits for one.
QUICK_FIX = "Quick Fix"


class Hugo(Kit):
    """Puts the stack-givers and other combatants' skills ahead of the attacks that spend the stacks."""

    name = "Hugo"
    cards = owned("Hugo")
    # Dingo Howling with the primers, Fan of Daggers first of the attacks, and Knife Toss, his filler, last of them.
    places = {"Dingo Howling": PHASE_PRIME, "Fan of Daggers": PHASE_ATTACK - 0.5, "Knife Toss": PHASE_ATTACK + 0.5}

    def phase(self, name, board, base):
        """Hold Quick Fix behind a stack-giver, and bring other combatants' skills forward of the attacks.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        card = base_name(name)
        if card == QUICK_FIX:
            # Stacks carry over, so a stack-giver played this turn or last is the best sign there is one to draw on.
            stacked = count((*board.played, *board.last_turn), STACKERS) > 0
            return base if stacked else PHASE_ATTACK - 0.25
        if base == PHASE_OTHER and borrowed(card, SKILL_CATEGORY, self.name):
            # Each feeds Hunting Instincts a stack, just ahead of Fan of Daggers.
            return PHASE_ATTACK - 0.75
        return super().phase(name, board, base)


KIT = Hugo()
