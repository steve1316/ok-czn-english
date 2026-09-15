"""Draw the Tasks tab's Info rows in reading order, and name the team above its equipment.

ok-script draws one row per `task.info` entry in insertion order, so upstream's order is simply the order
`log_credit` and `log_node_status` happen to write in: the version and game language near the top, the win rate
at the very bottom, and the run's position buried under five yes/no flags. The team's names are read once per
run and never shown at all.

Rows are re-sorted after `log_node_status` runs rather than written in order, because a row keeps the slot of
its first write and several are written by other handlers. The sort is stable, so the meditation rows keep their
own order and a row nobody ranked falls to the bottom instead of vanishing. A fresh dict is assigned rather than
the old one re-filled, so the GUI thread never sees `task.info` half empty.
"""

from ok import Logger

from src.en.handlers import loaded, register, wrap
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
# Names this change in the shared record of what a function already carries.
TAG = "reading order"

_patched = False


def rank(key):
    """Place one Info row in `ORDER`.

    Args:
        key: The row's key as stored in `task.info`.

    Returns:
        Its position, or one past the end for a row `ORDER` does not name.
    """
    if isinstance(key, str) and key.startswith(MEDITATING):
        return ORDER.index(MEDITATING)
    return ORDER.index(key) if key in ORDER else len(ORDER)


def in_reading_order(info):
    """Sort the Info rows into `ORDER`.

    Args:
        info: The task's `info` dict.

    Returns:
        A new dict holding the same rows in reading order.
    """
    return dict(sorted(info.items(), key=lambda item: rank(item[0])))


def reordering(handler):
    """Wrap `log_node_status` so the rows it has just written are drawn in reading order.

    Args:
        handler: The handler to wrap, upstream's or another patch's.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        handled = handler(task)
        info = getattr(task, "info", None)
        if info:
            ordered = in_reading_order(info)
            if list(ordered) != list(info):
                task.info = ordered
        return handled

    return wrapped


def install(utils):
    """Wrap the status reporter wherever the run reaches it.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "log_node_status", reordering, TAG)


def apply():
    """Draw the Info rows in reading order."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
