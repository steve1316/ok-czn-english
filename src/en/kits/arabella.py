"""Arabella: apply Fracture, detonate it, then finish, and leave her filler for spare Action Points.

Scream For Me and Hollow Verdict put Fracture on the enemies, Sadistic Restraint detonates it, and The Art of Unmaking grows with each harmful effect.
The generic picker plays by value, so Sadistic Restraint detonates before any Fracture is up and The Art of Unmaking opens the turn.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, Kit, base_name, owned

SCREAM = "Scream For Me"
HOLLOW = "Hollow Verdict"
SADISTIC = "Sadistic Restraint"
ART = "The Art of Unmaking"
# The cards that apply or detonate Fracture.
FRACTURE = frozenset({SCREAM, HOLLOW, SADISTIC})
# Both guides tell her to cut these, so they only take Action Points nothing else wants.
FILLER = frozenset({"Diagonal Slash", "Crimson Domain"})


def has(names):
    """Say whether any of some cards applies or detonates Fracture.

    Args:
        names: Canonical card names, from the hand or from what the turn has played.

    Returns:
        True when one is a Fracture card, in any Epiphany.
    """
    return any(base_name(name) in FRACTURE for name in names)


class Arabella(Kit):
    """Orders the Fracture cards, holds The Art of Unmaking behind them, and ranks her filler last."""

    name = "Arabella"
    cards = owned("Arabella")
    # Scream opens as a primer, Hollow leads the attacks, then The Art of Unmaking, and Sadistic detonates last.
    places = {SCREAM: PHASE_PRIME, HOLLOW: PHASE_ATTACK - 0.5, ART: PHASE_ATTACK + 0.25, SADISTIC: PHASE_ATTACK + 0.5}

    def held(self, name, board):
        """Keep The Art of Unmaking until a Fracture card has been played, when one is in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for The Art of Unmaking with no harmful effect on the target yet.
        """
        return base_name(name) == ART and has(board.hand) and not has(board.played)

    def worth(self, name, board, base, rate):
        """Rank her filler last while a Fracture card is in hand.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name.

        Returns:
            The value to plan with.
        """
        return 0 if base_name(name) in FILLER and has(board.hand) else base


KIT = Arabella()
