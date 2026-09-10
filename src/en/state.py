"""Say what the run decided, once, instead of once a frame.

The handlers that judge a screen run on every tick that screen is up, so a decision they take is a decision
they take three or four times a second. Upstream's answer to that was mostly to say nothing at all, which is
why a log could run to 33 MB a day and still not tell you why a piece of equipment was passed over.

`say_once` is the other answer: log the decision the first time it is reached and stay quiet while it holds.
A tag groups the lines a category writes so one of them can be pulled out of a day's file with `grep -F`,
which is the workflow the tags exist for.

What is remembered lives on the task, alongside `_en_turn` and the rest of the fork's per-run state, and it is
dropped when `task.info` is empty. That is the framework's own start-of-run signal - `_mark_task_enabled`
calls `info_clear()` - so a second run says everything afresh rather than inheriting the first run's idea of
what has already been mentioned. `src/en/stuck.py` exists because a cached value outlived its run once
already.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# Where the last line said under each tag is kept, per task.
SAID = "_en_said"

# The categories a line can belong to. One per thing the run decides, so `grep -F "[gear]"` pulls a day's
# equipment and shop decisions out of a file that also holds every card played.
RUN = "run"
CARD = "card"
BATTLE = "battle"
GEAR = "gear"


def say_once(task, tag, message):
    """Log a decision unless this task's last line under the same tag said exactly it.

    Args:
        task: The running task, which is where the memo lives.
        tag: The category this line belongs to, such as `gear` or `battle`.
        message: The line to log, without its tag.

    Returns:
        True when the line was logged, False when it repeated the last one.
    """
    said = getattr(task, SAID, None)
    if said is None:
        said = {}
        setattr(task, SAID, said)
    # An empty Info dict means the framework has just cleared it for a new run.
    if not getattr(task, "info", None):
        said.clear()
    if said.get(tag) == message:
        return False
    said[tag] = message
    logger.info(f"[{tag}] {message}")
    return True
