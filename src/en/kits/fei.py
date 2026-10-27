"""Fei: set up with Exorcist's Formation, cash in with Blazing War Dance late, and keep the Action Points for Soulfire Dance.

Descent comes from draws once Formation is out, Blazing War Dance returns an Inferno Rhapsody per Descent gained this turn, and Soulfire
Dance scales with the points it is left. The generic picker draws before Formation, fires War Dance first, and spends points ahead of Soulfire.
"""

from src.en.kits.kit import PHASE_FREE, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

# Formation goes before every draw, so the draws gain Descent and Soliloquy cannot discard it.
FORMATION = "Exorcist\u2019s Formation"
# Moves Rhapsodies back for each Descent gained this turn, so it goes after the draws and just before Soulfire Dance.
WAR_DANCE = "Blazing War Dance"
# Spends every point left, so the one-point cards that would shrink it are held while it is in hand.
SOULFIRE = "Soulfire Dance"
SMALL_SPENDS = frozenset({"Azure Flame", "Melancholy"})


class Fei(Kit):
    """Orders Formation and Blazing War Dance, and holds the small cards that would shrink Soulfire Dance."""

    name = "Fei"
    cards = owned("Fei")
    # Formation before the free draws, and War Dance after nearly everything.
    places = {FORMATION: PHASE_FREE - 0.5, WAR_DANCE: PHASE_SPENDS_EVERYTHING - 0.5}

    def held(self, name, board):
        """Keep Azure Flame and Melancholy while Soulfire Dance could take their points.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a one-point card with Soulfire Dance in hand.
        """
        return base_name(name) in SMALL_SPENDS and any(base_name(other) == SOULFIRE for other in board.hand)


KIT = Fei()
