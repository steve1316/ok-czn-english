"""Rei: buff first, so the attacks that follow hit harder.

Strike of Darkness, Dark Condensation and Predator's Blade all raise the damage of attacks played after them for one turn.
The generic picker files the first and last as plain attacks and Dark Condensation as a skill, so they land after the hits they buff.
"""

from src.en.kits.kit import PHASE_PRIME, Kit, owned


class Rei(Kit):
    """Plays her three buffs ahead of the attacks, the basic-attack buff first and the team Morale last."""

    name = "Rei"
    cards = owned("Rei")
    # Strike of Darkness buffs basic attacks, Dark Condensation one chosen attack, and Predator's Blade gives the team Morale just before the hits.
    places = {"Strike of Darkness": PHASE_PRIME - 0.5, "Dark Condensation": PHASE_PRIME, "Predator's Blade": PHASE_PRIME + 0.25}


KIT = Rei()
