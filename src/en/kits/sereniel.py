"""Sereniel: make Homing Lasers first, build Afterglow with them, then cash it in with Pale Shooting Star and Cobalt Light.

Shining Core creates Homing Laser L, lasers build Afterglow, and an attack then breaks Tenacity into a Ravage that returns the lasers.
The generic picker plays Shining Core as late filler and buys Cobalt Light cold, before any laser has built Afterglow for it to cash in.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_SETUP, Kit, base_name, count, owned

# Both spellings of the laser: the starter and the one Shining Core creates.
LASERS = frozenset({"Homing Laser", "Homing Laser L"})
CORE = "Shining Core"
COBALT = "Cobalt Light"
PALE = "Pale Shooting Star"
# Lasers that must fire before each cash-in card, for the Afterglow it needs. Cobalt Light has to Ravage to refund its points.
UNLOCK = {COBALT: 2, PALE: 1}


def coming(board):
    """Say whether a laser is in hand or Shining Core is about to make some.

    Args:
        board: The `cards.Board` the hand is in.

    Returns:
        True when a laser will be played this turn without anything else drawn.
    """
    return count(board.hand, LASERS | {CORE}) > 0


class Sereniel(Kit):
    """Plays Shining Core first, and holds Cobalt Light and Pale Shooting Star until lasers have fired for them to cash in."""

    name = "Sereniel"
    cards = owned("Sereniel")
    # Shining Core with the setup cards, so its lasers are there for the whole chain. Cobalt Light after the other attacks.
    places = {CORE: PHASE_SETUP, COBALT: PHASE_ATTACK + 0.5}

    def held(self, name, board):
        """Keep Cobalt Light and Pale Shooting Star until enough lasers fired, while more lasers are still to come.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a cash-in card the lasers have not yet built up for.
        """
        needed = UNLOCK.get(base_name(name))
        return needed is not None and coming(board) and count(board.played, LASERS) < needed


KIT = Sereniel()
