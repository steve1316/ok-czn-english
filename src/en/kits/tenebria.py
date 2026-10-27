"""Tenebria: play Rhythm cards, then Encore straight after one, and keep Call & Response in hand as a Rhythm.

Call & Response counts as a Rhythm while it sits in hand, Encore only procs a Rhythm played just before it, and Spotlight returns a
played Rhythm. The generic picker plays Call & Response and Spotlight early and Encore at random, so all three lose their bonus.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_ESCAPE, Kit, base_name, owned

CALL = "Call & Response"
ENCORE = "Encore"
SPOTLIGHT = "Spotlight"
# Every Rhythm card, base or from Music, Start!, begins its name with this.
RHYTHM = "Rhythm"


def rhythms(names):
    """Count the Rhythm cards among some cards.

    Args:
        names: Canonical card names, from the hand or from what the turn has played.

    Returns:
        How many are Rhythm cards of any kind.
    """
    return sum(base_name(name).startswith(RHYTHM) for name in names)


class Tenebria(Kit):
    """Holds Call & Response and Spotlight while Rhythms are in hand, and Encore until a Rhythm was the last card played."""

    name = "Tenebria"
    cards = owned("Tenebria")
    # Encore the moment a Rhythm was the last card played, before anything else can come between. Call & Response last of the attacks.
    places = {ENCORE: PHASE_ESCAPE + 0.5, CALL: PHASE_ATTACK + 0.5}

    def held(self, name, board):
        """Keep Call & Response while a Rhythm is in hand, Spotlight until one is played, and Encore until one is the last card played.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a card whose bonus the turn has not yet earned.
        """
        card = base_name(name)
        if card == CALL:
            return bool(rhythms(board.hand))
        if card == SPOTLIGHT:
            # With no Rhythm in hand there is nothing to wait for, and Spotlight fetches one.
            return bool(rhythms(board.hand)) and not rhythms(board.played)
        if card == ENCORE:
            return not rhythms(board.played[-1:])
        return False


KIT = Tenebria()
