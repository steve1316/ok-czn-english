"""Send a Windows notification at the few points in a run worth looking up for.

Errors are left alone: the executor already raises a notification of its own when a task stops on one.
"""

import time

from ok import Logger

from src.en.handlers import loaded, register, replace
from src.en.stuck import CLOCK

logger = Logger.get_logger(__name__)

# How long one screen has to sit unchanged before it is worth telling someone about, and how long to wait
# before saying so again. Upstream's own fallback handling starts at 10s, so this is well past that.
STUCK_SECONDS = 60
REPEAT_SECONDS = 300

# Where the run keeps its score. The floor is counted from the bosses cleared, so it is one ahead of them.
ROUNDS = "total_rounds"
WINS = "success_rounds"
BOSSES = "pass_final_boss_count"

# Set on the task, to keep one stuck screen from sending a notification on every frame.
LAST_STUCK = "_en_last_stuck_notice"

_patched = False


def announce(task, message):
    """Log a line and raise a Windows notification for it.

    Args:
        task: The running task, whose name titles the notification.
        message: The line to show, in English so the catalog leaves it alone.
    """
    task.log_info(message)
    # The title goes through the app catalog on the way out, which turns the mode's Chinese name into the one
    # shown in the app. Sending it as the title rather than the message keeps the toast readable at a glance.
    task.notification(message, title=task.name, tray=True)


def score_of(task):
    """Read the run counters off a task.

    Args:
        task: The running task.

    Returns:
        A `(rounds, wins, floor)` triple, all zero when the task has no counters yet.
    """
    status = getattr(task, "node_status", None) or {}
    return status.get(ROUNDS, 0), status.get(WINS, 0), status.get(BOSSES, 0) + 1


def starting(original_enable, task):
    """Wrap a mode's `enable` so starting it says so.

    Args:
        original_enable: The mode's own `enable`, which the Start button reaches through the run loop.
        task: The mode being wrapped.

    Returns:
        The replacement `enable`.
    """
    def enable():
        original_enable()
        announce(task, "Run started.")

    return enable


def finishing(original):
    """Wrap the expedition result page so a finished run reports its score.

    Args:
        original: Upstream's `handle_expedition_result`.

    Returns:
        The wrapped handler.
    """
    def handle_expedition_result_announcing(task):
        # Read the floor first. The original clears the per-run status before it returns, so by then the
        # count of bosses cleared is already back to zero.
        before, _, floor = score_of(task)
        handled = original(task)
        rounds, wins, _ = score_of(task)
        if rounds > before:
            announce(task, f"Run finished on floor {floor}. {wins} of {rounds} runs have succeeded.")
        return handled

    return handle_expedition_result_announcing


def stuck(original):
    """Wrap the stuck-screen handler so a screen nothing can get past is reported.

    Upstream already tries to click its way out after ten seconds. This only speaks up once that has been
    failing long enough to be worth a look, and then at most once every few minutes.

    Args:
        original: Upstream's `handle_stuck_log`.

    Returns:
        The wrapped handler.
    """
    def handle_stuck_log_announcing(task):
        handled = original(task)
        changed = getattr(task, CLOCK, None)
        if changed is None:
            return handled
        seconds = time.time() - changed
        if seconds < STUCK_SECONDS:
            # The screen is moving again, so the next spell gets to report straight away.
            setattr(task, LAST_STUCK, 0)
            return handled
        if time.time() - getattr(task, LAST_STUCK, 0) >= REPEAT_SECONDS:
            setattr(task, LAST_STUCK, time.time())
            announce(task, f"Stuck on the same screen for {int(seconds)}s.")
        return handled

    return handle_stuck_log_announcing


def apply():
    """Announce the start of a run, the end of one, and a screen the bot cannot get past."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None:
            return
        for name, wrap in (("handle_expedition_result", finishing), ("handle_stuck_log", stuck)):
            handler = getattr(utils, name, None)
            if handler is not None:
                replace(name, wrap(handler))

    register(install)

    try:
        from ok.task.task import BaseTask, TriggerTask
    except ImportError:
        logger.warning("could not import BaseTask, the start of a run will not be announced")
        _patched = True
        return

    original_load_config = BaseTask.load_config

    def patched_load_config(self):
        # Wrapping here is what puts this ahead of the run loop, which takes its own reference to `enable`
        # when the mode moves to the Tasks tab. Only the modes have a run to announce.
        if isinstance(self, TriggerTask):
            self.enable = starting(self.enable, self)
        original_load_config(self)

    BaseTask.load_config = patched_load_config
    _patched = True
