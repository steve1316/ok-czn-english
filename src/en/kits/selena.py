"""Selena: lay down Marks first, so every attack card after them fires an extra attack.

High-Power Scope and Target Spotted give Marks, and each attack card played while Marks remain fires an extra attack and uses one up.
The generic picker plays High-Power Scope after the attacks, when its Marks have nothing to spend on until next turn.
"""

from src.en.kits.kit import PHASE_ATTACK, PHASE_PRIME, Kit, owned


class Selena(Kit):
    """Plays High-Power Scope ahead of every attack, then the attacks that give Marks or Weakness ahead of the rest."""

    name = "Selena"
    cards = owned("Selena")
    # Scope first, then Target Spotted for a Mark of its own, then Drone Bombing's Weakness, all ahead of the plain attacks.
    places = {"High-Power Scope": PHASE_PRIME, "Target Spotted": PHASE_ATTACK - 0.25, "Drone Bombing": PHASE_ATTACK - 0.1}


KIT = Selena()
