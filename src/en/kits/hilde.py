"""Hilde: fill the draw pile with Quiver Reload, set up her buffs, and play Vortex Arrow last of the draws.

Quiver Reload puts Homing Arrows in the draw pile for every draw to pull, and Vortex Arrow gains damage for each attack card drawn this turn.
The generic picker plays Quiver Reload with the fillers after the draws, and Vortex Arrow first, before Draw & Release has drawn anything.
"""

from src.en.kits.kit import PHASE_SETUP, Kit, base_name, owned

QUIVER = "Quiver Reload"
# Card the Quiver is priced against, since both set up the draws that follow.
DRAW_AND_RELEASE = "Draw & Release"
# Hits harder for each attack card drawn this turn, so it goes after every other draw.
VORTEX = "Vortex Arrow"


class Hilde(Kit):
    """Orders the Quiver, her buffs and the draws ahead of Vortex Arrow, and keeps the Quiver in the turn's budget."""

    name = "Hilde"
    cards = owned("Hilde")
    # Quiver Reload, then Big Game Ranger, then Plasma Rain, all ahead of the draws at `PHASE_SETUP`, then Vortex Arrow after them.
    places = {QUIVER: PHASE_SETUP - 0.5, "Big Game Ranger": PHASE_SETUP - 0.25, "Plasma Rain": PHASE_SETUP - 0.1, VORTEX: PHASE_SETUP + 0.5}

    def worth(self, name, board, base, rate):
        """Price Quiver Reload as high as Draw & Release, which it fuels, so the turn's points reach it.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here Draw & Release's.

        Returns:
            The value to plan with.
        """
        if base_name(name) == QUIVER:
            return max(base, rate(DRAW_AND_RELEASE))
        return base


KIT = Hilde()
