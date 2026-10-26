"""Yuki: enable Inspiration with Trickery Strike before the attacks, and finish on Iceberg Cleave.

Trickery Strike enables Inspiration on the cards in her hand, so it only helps the attacks played after it. Flash Slash opens and Iceberg
Cleave pays off. The generic picker plays Trickery Strike among the attacks and Iceberg Cleave first, on value per point.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, Kit, owned


class Yuki(Kit):
    """Moves Trickery Strike up to the primers and Iceberg Cleave to the end of the attacks."""

    name = "Yuki"
    cards = owned("Yuki")
    places = {"Trickery Strike": PHASE_PRIME, "Iceberg Cleave": PHASE_ATTACK + 0.5}


KIT = Yuki()
