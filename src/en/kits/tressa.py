"""Tressa: Curse first, then the dagger makers, then the daggers, and the Advanced Shadow Dagger after them.

Curse adds Agony only to Attacks played after it, and Unsheathe Dagger and Shadow Reload create the Shadow Daggers she spends her turn on.
The generic picker plays Curse among the daggers, the makers after Dagger Throw, and the Advanced Shadow Dagger early.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_FREE, PHASE_SETUP, Kit, owned


class Tressa(Kit):
    """Moves Curse, the dagger makers and the Advanced Shadow Dagger to where their effects land."""

    name = "Tressa"
    cards = owned("Tressa")
    # Curse ahead of every other free card. The makers with the setup cards. The Advanced Shadow Dagger, which Retains and grows with Agony, last.
    places = {
        "Curse": PHASE_FREE - 0.5,
        "Unsheathe Dagger": PHASE_SETUP,
        "Shadow Reload": PHASE_SETUP,
        "Advanced Shadow Dagger": PHASE_ATTACK + 0.5,
    }


KIT = Tressa()
