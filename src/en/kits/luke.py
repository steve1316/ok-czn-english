"""Luke: make Handgun Bullets, fire them, then cash them in with Finisher Round and Dance of the Demon.

Finisher Round is Unactivatable until five Handgun Bullets have fired this turn, and Dance of the Demon gains a hit per Bullet fired.
The generic picker tries the free 500% Finisher Round first every turn, and plays the bullet makers and Dance in hand order.
"""

from src.en.kits.kit import PHASE_FREE, PHASE_SPENDS_EVERYTHING, Kit, base_name, count, owned

# The Handgun Bullets his cards create. All four are free attacks.
BULLETS = frozenset({"Magnum Shot", "Silver Shot", "Uranium Shot", "Tracer Shot"})
# Cards that create Handgun Bullets, so they go before the bullets do.
MAKERS = frozenset({"Stealth Reload", "Chain Fire"})
# Bullets Stealth Reload creates before any Epiphany, which the data leaves as X.
RELOADED = 2
# Buffs the next Bullet fired, so it goes after the makers and before the bullets.
SEIZE = "Seize the Opportunity"
FINISHER = "Finisher Round"
# Handgun Bullets that must fire this turn before Finisher Round can be played. The count starts again every turn.
FINISHER_UNLOCK = 5
DANCE = "Dance of the Demon"


class Luke(Kit):
    """Holds Finisher Round until it unlocks, orders the turn around the bullets, and prices Dance by the bullets it will follow."""

    name = "Luke"
    cards = owned("Luke") | BULLETS
    # Makers, then Seize, then the free bullets at `PHASE_FREE`, then Finisher Round. Dance waits for every bullet but still beats an X-cost card.
    places = {
        **dict.fromkeys(MAKERS, PHASE_FREE - 0.5),
        SEIZE: PHASE_FREE - 0.25,
        FINISHER: PHASE_FREE + 0.5,
        DANCE: PHASE_SPENDS_EVERYTHING - 0.5,
    }

    def held(self, name, board):
        """Keep Finisher Round until enough Handgun Bullets have fired this turn to unlock it.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Finisher Round the game would still refuse.
        """
        return base_name(name) == FINISHER and count(board.played, BULLETS) < FINISHER_UNLOCK

    def worth(self, name, board, base, rate):
        """Price the bullet makers by the bullets they bring, and Dance of the Demon by the bullets it will follow.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here the bullets'.

        Returns:
            The value to plan with.
        """
        card = base_name(name)
        if card == "Stealth Reload":
            # Which bullets it creates is random, so each is worth an average one.
            return RELOADED * sum(rate(bullet) for bullet in BULLETS) / len(BULLETS)
        if card == DANCE:
            # Every bullet in hand goes before it, so each one there is a hit it will have.
            return base * (1 + count(board.played, BULLETS) + count(board.hand, BULLETS))
        return base


KIT = Luke()
