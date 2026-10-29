"""Pick the Sortie boss the team's damage dealers can hit for weakness damage.

Upstream picks one of the two bosses at random, though each shows the attribute it is weak to and the team's attributes are known.
"""

from collections import Counter

from ok import Logger

from src.en import board
from src.en.battle import PARTY
from src.en.game_battle import COMBATANT_ATTRIBUTE
from src.en.game_quality import COMBATANT_ROLE
from src.en.handlers import StandIn, loaded, register, replace, standing_in
from src.en.screen import frame_of, patch_of

logger = Logger.get_logger(__name__)

# Healers and protectors hit too weakly for their attribute to be worth choosing a boss over.
NOT_DAMAGE = frozenset({"Healing", "Protection"})
# Where each boss's Weakness badge sits, keyed by the point upstream reads that boss's name at.
BADGES = {(0.358, 0.706): (0.444, 0.755), (0.641, 0.706): (0.7245, 0.755)}

_patched = False


def dealers(party):
    """Count the team's damage dealers by attribute.

    Args:
        party: Names of the combatants on the team, from `battle.PARTY`.

    Returns:
        A `Counter` of attribute names.
    """
    return Counter(COMBATANT_ATTRIBUTE[name] for name in party if name in COMBATANT_ATTRIBUTE and COMBATANT_ROLE.get(name) not in NOT_DAMAGE)


def weakness(frame, boss):
    """Read the attribute one boss is weak to off its Weakness badge.

    Args:
        frame: The boss select screen.
        boss: One of upstream's boss entries, holding the `x` and `y` its name was read at.

    Returns:
        The attribute name, or None when the badge cannot be read.
    """
    point = BADGES.get((boss["x"], boss["y"]))
    if point is None:
        return None
    patch = patch_of(frame, board.box_around(*point, board.WEAKNESS_HALF))
    return board.attribute_of(patch, beside_counter=False, saturation_floor=board.BOSS_BADGE_SATURATION)


class WeakBoss(StandIn):
    """Stands in for the module's `random` at the boss select screen, so the pick goes to a boss the team can hit for weakness damage."""

    def __init__(self, original, task):
        """Hold the module being stood in for and the task whose screen and team decide the pick.

        Args:
            original: The module upstream would otherwise have used.
            task: The running task.
        """
        super().__init__(original)
        self.task = task

    def choice(self, options):
        """Choose among the bosses whose weakness the most damage dealers on the team share, at random among a tie.

        Args:
            options: Upstream's boss entries, each with its `name`, `x` and `y`.

        Returns:
            One of the best-matched bosses, or one of all of them when no weakness matches the team.
        """
        options = list(options)
        frame = frame_of(self.task)
        hitting = dealers(getattr(self.task, PARTY, frozenset()))
        weak = [weakness(frame, option) for option in options]
        scores = [hitting[attribute] if attribute else 0 for attribute in weak]
        best = [option for option, score in zip(options, scores) if score == max(scores, default=0)]
        logger.info(f"bosses weak to {dict(zip((option['name'] for option in options), weak))}, team hits with {dict(hitting)}, "
                    f"choosing among {[option['name'] for option in best]}")
        return self.original.choice(best or options)


def apply():
    """Run upstream's boss select with a pick that favours the boss weak to the team's damage."""
    global _patched
    if _patched:
        return

    def install():
        utils_sortie = loaded("utils_sortie")
        if utils_sortie is None:
            return
        original = utils_sortie.handle_boss_selection

        def handle_boss_selection(task):
            """Run upstream's boss select, choosing by weakness rather than at random.

            Args:
                task: The running task.

            Returns:
                Whatever upstream's own handler returns.
            """
            with standing_in(utils_sortie, random=WeakBoss(utils_sortie.random, task)):
                return original(task)

        replace("handle_boss_selection", handle_boss_selection)

    register(install)
    _patched = True
