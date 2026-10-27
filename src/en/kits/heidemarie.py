"""Heidemarie: play every other card first, start the Linked chain with exactly one Linked card, then cash in with Effulgent Release.

Playing one Linked card discards the other Linked cards in hand, which fires their Quietus and makes Blades hit for free. The generic picker
buys Linked cards one by one, plays Expansion after the attacks, and plays the useless Effulgent Compression and Release first.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_SETUP, PHASE_SPENDS_EVERYTHING, Kit, base_name, owned

# Cards that are Linked, so playing one discards the rest.
LINKED = frozenset({"Effulgent Blade", "Sword Rain", "Thread of Light"})
# Unusable by hand and brought back by a discard, so the kit never plays it.
COMPRESSION = "Effulgent Compression"
# Makes Blades for the chain, so before it in the turn, but only in its plain form, which an Epiphany can change.
EXPANSION = "Effulgent Expansion"
# The free nuke the chain unlocks, so it goes after the chain.
RELEASE = "Effulgent Release"


class Heidemarie(Kit):
    """Holds back Compression and the Linked cards the chain has discarded, and puts the starter after the other cards."""

    name = "Heidemarie"
    # Blades, Compression and Release are made mid-fight, so the data never names them hers, and a hand of only those still needs the kit.
    cards = owned("Heidemarie") | {"Effulgent Blade", COMPRESSION, RELEASE}
    # The Linked starter after the other attacks, and Release after the starter.
    places = {**dict.fromkeys(LINKED, PHASE_ATTACK + 0.5), RELEASE: PHASE_SPENDS_EVERYTHING - 0.5}

    def held(self, name, board):
        """Keep Compression always, and the Linked cards once one has been played this turn.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a card the kit never plays here.
        """
        card = base_name(name)
        if card == COMPRESSION:
            return True
        return card in LINKED and any(base_name(played) in LINKED for played in board.played)

    def phase(self, name, board, base):
        """Play a plain Effulgent Expansion ahead of the attacks, so its Blades are in hand for the chain.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            The card's place in the turn.
        """
        if name == EXPANSION:
            return PHASE_SETUP - 0.5
        return super().phase(name, board, base)


KIT = Heidemarie()
