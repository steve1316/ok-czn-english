"""Draw the Tasks tab's Info rows in reading order, and name the team above its equipment.

ok-script draws one row per `task.info` entry in insertion order, so upstream's order is simply the order
`log_credit` and `log_node_status` happen to write in: the version and game language near the top, the win rate
at the very bottom, and the run's position buried under five yes/no flags. The team's names are read once per
run and never shown at all.

Rows are re-sorted in `info_set` whenever a new one appears, since a row keeps the slot of its first write and
they are written by several handlers. It wraps the raw method, under `log_text`'s translation, so keys arrive in
English. The sort is stable, so meditation rows keep their own order and an unranked row falls to the bottom
instead of vanishing. A fresh dict is assigned rather than the old one re-filled, so the GUI never sees it half empty.
"""

from ok import Logger

from src.en.log_strings import MESSAGES, TEMPLATES

logger = Logger.get_logger(__name__)

# The row this fork adds. It is English already, so it needs no catalog entry.
COMBATANTS = "Combatants"
# The framework's own row for the last logged line.
LOG = "Log"
# What every meditation row's key starts with once translated. One row per card, so they rank as a group.
MEDITATING = TEMPLATES["冥想：{}"].split("{0}")[0]
# Top to bottom: what moves during a run, then the one-way flags, then what never changes. Keys are the translated
# ones, since `log_text` respells them before they are stored.
ORDER = (
    LOG,
    MESSAGES["所处层数，节点，类型"],
    MESSAGES["当前信用点"],
    MESSAGES["当前胜率"],
    COMBATANTS,
    MESSAGES["装备信息"],
    MESSAGES["本局已移除卡牌"],
    MESSAGES["本局已获得中立牌"],
    MEDITATING,
    MESSAGES["是否到达关底boss"],
    MESSAGES["是否进入关底boss战斗"],
    MESSAGES["是否已逃脱"],
    MESSAGES["是否已获得特定闪光"],
    MESSAGES["获取刷存档主战员头像"],
    MESSAGES["游戏语言"],
    MESSAGES["版本号"],
)
# Each ranked row's position in `ORDER`.
RANKS = {key: position for position, key in enumerate(ORDER)}

_patched = False


def rank(key):
    """Place one Info row in `ORDER`.

    Args:
        key: The row's key as stored in `task.info`.

    Returns:
        Its position, or one past the end for a row `ORDER` does not name.
    """
    return RANKS[MEDITATING] if key.startswith(MEDITATING) else RANKS.get(key, len(ORDER))


def ordering(original):
    """Wrap `info_set` so a new row is drawn in its place in `ORDER` rather than at the bottom.

    Args:
        original: The unbound `info_set` being replaced.

    Returns:
        The replacement.
    """
    def info_set_in_order(self, key, value):
        new = key not in self.info
        result = original(self, key, value)
        if new:
            self.info = dict(sorted(self.info.items(), key=lambda item: rank(item[0])))
        return result

    return info_set_in_order


def apply():
    """Draw the Info rows in reading order."""
    global _patched
    if _patched:
        return

    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, the Info rows will stay in upstream's order")
        _patched = True
        return

    BaseTask.info_set = ordering(BaseTask.info_set)
    _patched = True
