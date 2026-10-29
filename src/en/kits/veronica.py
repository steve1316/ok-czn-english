"""Veronica: set up Reload, never touch the Ballistas, which fire themselves at the end of the turn.

Firing Preparation makes a Ballista every turn, Bombardment Prep and Pendant of Resolution feed the Reload that boosts them, and every
Ballista is unplayable. The generic picker lists the Ballistas as free Attacks and plays them first, ahead of the setup cards.
"""

from src.en.kits.kit import PHASE_UPGRADE, Kit, base_name, owned

# Every Ballista a card can create. They fire on their own at the end of the turn.
BALLISTAS = frozenset({"Ballista", "Piercing Ballista", "Enhanced Ballista", "Giant Ballista", "Shelling Ballista", "Micro Ballista"})


class Veronica(Kit):
    """Holds every Ballista, and plays Firing Preparation, Bombardment Prep and Pendant of Resolution first."""

    name = "Veronica"
    # The Ballistas too, so the kit is still on when they are the only cards left in hand.
    cards = owned("Veronica") | BALLISTAS
    # Firing Preparation is the engine, then Bombardment Prep before Reload comes in, then Pendant before the skills that trigger it.
    places = {"Firing Preparation": PHASE_UPGRADE, "Bombardment Prep": PHASE_UPGRADE + 0.25, "Pendant of Resolution": PHASE_UPGRADE + 0.5}

    def held(self, name, board):
        """Keep every Ballista in hand.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Ballista.
        """
        return base_name(name) in BALLISTAS


KIT = Veronica()
