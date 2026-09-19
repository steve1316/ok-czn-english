"""Draw the Tasks tab's Info rows in reading order, name the team above its equipment, and show the table while idle.

ok-script draws one row per `task.info` entry in insertion order, so upstream's order is simply the order
`log_credit` and `log_node_status` happen to write in: the version and game language near the top, the win rate
at the very bottom, and the run's position buried under five yes/no flags. The team's names are read once per
run and never shown at all.
"""

import types

from ok import Logger

from src.en.framework import import_ui
from src.en.log_strings import MESSAGES, TEMPLATES

logger = Logger.get_logger(__name__)

# The row this fork adds. It is English already, so it needs no catalog entry.
COMBATANTS = "Combatants"
# What the team's row holds until a run reaches the Combatants screen and reads it. The row is drawn either
# way, because a row that appears partway through a run reads as the table rearranging itself.
UNREAD = "-"
# The framework's own row for the last logged line.
LOG = "Log"
# The equipment row, and where the run keeps the reading that fills it. Upstream fills that row from a ledger
# of what the run installed rather than from anything on screen, so `src/en/equipment.py` reads the Combatants
# screen and leaves the line here. Absent until it has, which is what `UNREAD` says.
GEAR = MESSAGES["装备信息"]
TEAM_GEAR = "_en_team_gear"
# The win rate row, and the tail upstream gives it when no run has finished: before any run finishes upstream
# divides by zero and the row reads `0/0 NaN`. `NO_RUNS` is what it reads as instead.
WIN_RATE = MESSAGES["当前胜率"]
UNDIVIDED = " NaN"
NO_RUNS = " (0%)"
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
# The rows a run fills in once it is under way. Every key `ORDER` ranks except the meditation group, which is
# one row per configured card rather than a key, and is left to arrive with the first status report.
STARTED = tuple(key for key in ORDER if key != MEDITATING)
# The mode setting the Game Language row reads, the same one `log_node_status` reports.
GAME_LANGUAGE = "游戏语言"
# The table's title before any task has run.
IDLE = "Idle"
# Where a tab remembers its X was clicked before any run, when upstream's own dismissal has no run to key on.
IDLE_DISMISSED = "_en_idle_dismissed"
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


def in_order(rows):
    """Sort info rows into reading order.

    Args:
        rows: The rows to draw, keyed the way `task.info` keys them.

    Returns:
        A new dict in `ORDER`, which both the live table and the idle one are built through.
    """
    return dict(sorted(rows.items(), key=lambda row: rank(row[0])))


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
            self.info = in_order(self.info)
        return result

    return info_set_in_order


def zeroing_win_rate(original):
    """Wrap `info_set` so a win rate with no finished runs reads 0% rather than upstream's NaN.

    Args:
        original: The unbound `info_set` being replaced.

    Returns:
        The replacement.
    """
    def info_set_zeroed(self, key, value):
        if key == WIN_RATE and value.endswith(UNDIVIDED):
            value = value.removesuffix(UNDIVIDED) + NO_RUNS
        return original(self, key, value)

    return info_set_zeroed


def showing_what_is_worn(original):
    """Wrap `info_set` so the Equipment row reports what was read off the screen, not what the run installed.

    Upstream's own value is a ledger: blank at the start of every run, written only by an install, and kept
    for the save-data combatant alone, so a team wearing gear read as three empty slots. Substituting as the
    row is written keeps one write per tick, and so keeps `log_text`'s suppression of unchanged rows working.

    Args:
        original: The unbound `info_set` being replaced.

    Returns:
        The replacement.
    """
    def info_set_as_worn(self, key, value):
        if key == GEAR:
            value = getattr(self, TEAM_GEAR, None) or UNREAD
        return original(self, key, value)

    return info_set_as_worn


def seeding_the_table(original):
    """Wrap `info_clear` so a starting run's table is its full height from the first frame.

    Written straight into the dict rather than through `info_set`, which would log fifteen rows at INFO on
    every Start and re-sort the table once per row for an order `STARTED` is already in.

    Args:
        original: The unbound `info_clear` being replaced.

    Returns:
        The replacement.
    """
    def info_clear_seeded(self):
        original(self)
        # `node_status` is built in a mode's `__init__`, so it is there to be asked long before a Start. Story
        # has none, and runs none of the handlers that would fill these rows.
        if getattr(self, "node_status", None) is None:
            return
        for key in STARTED:
            self.info[key] = UNREAD

    return info_clear_seeded


def idle_rows(tasks):
    """Build the rows that are known before any run, in reading order.

    Args:
        tasks: The tab's tasks. The first one carrying a game language setting supplies that row.

    Returns:
        The rows, as the dict `update_task_info` draws.
    """
    from src.config import version

    rows = {COMBATANTS: UNREAD, MESSAGES["版本号"]: str(version).strip() or "dev"}
    for task in tasks:
        language = (getattr(task, "config", None) or {}).get(GAME_LANGUAGE)
        if language:
            rows[MESSAGES[GAME_LANGUAGE]] = language
            break
    return in_order(rows)


def showing_while_idle(original):
    """Wrap `TaskTab.update_info_table` so the table is on screen before any task has run.

    Args:
        original: The unbound `update_info_table` being replaced.

    Returns:
        The replacement.
    """
    def update_info_table(self):
        original(self)
        if self.last_task is not None or getattr(self, IDLE_DISMISSED, False):
            return
        tasks = getattr(self, "tasks", None)
        if not tasks:
            return
        self.update_task_info(types.SimpleNamespace(info=idle_rows(tasks), enabled=False, start_time=0, name=""))
        self.task_info_container.titleLabel.setText(IDLE)

    return update_info_table


def dismissing_while_idle(original):
    """Wrap `TaskTab.close_task_info` so the X also hides the idle table, which has no run to remember it by.

    Args:
        original: The unbound `close_task_info` being replaced.

    Returns:
        The replacement.
    """
    def close_task_info(self):
        if self.last_task is None:
            setattr(self, IDLE_DISMISSED, True)
        return original(self)

    return close_task_info


def apply():
    """Draw the Info rows in reading order, and keep the table on screen while idle."""
    global _patched
    if _patched:
        return

    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, the Info rows will stay in upstream's order")
    else:
        BaseTask.info_set = ordering(zeroing_win_rate(showing_what_is_worn(BaseTask.info_set)))
        BaseTask.info_clear = seeding_the_table(BaseTask.info_clear)

    task_tab = import_ui("tasks.TaskTab", "TaskTab")
    if task_tab is not None:
        task_tab.update_info_table = showing_while_idle(task_tab.update_info_table)
        task_tab.close_task_info = dismissing_while_idle(task_tab.close_task_info)
    _patched = True
