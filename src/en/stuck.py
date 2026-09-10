"""Give each run its own stuck clock instead of one shared with every run before it.

Upstream decides a screen has frozen by keeping two things on the task: `_last_change_time`, the moment the
picture last changed, and `_prev_frame_gray`, the picture it last compared against. Ten seconds without a
change and `handle_stuck_log` starts clicking its way out, beginning with the page's close button.

Neither is cleared when a run ends, and the mode object outlives the run - the Start button re-enables the
same instance - so the clock keeps counting through however long the app sat stopped. Start a run on the
screen the last one left up and the very first frame reports the whole idle spell as frozen time, closing a
page the run was about to read. One session shut the Combatants screen on four restarts running, each
reporting a longer freeze than the last (11s, 17s, 26s, 44s), every one of them measured from the first frame
of the first run.

Clearing both on the way into a run is the whole fix: nothing was watched while the task was stopped, so
nothing about that time can be counted as a frozen screen. What is knowingly left alone is the same staleness
inside a run - the detector only looks on frames that reach it, so a spell where a higher-priority handler
keeps taking the frame is unwatched too, and is still counted.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# What upstream's `is_frame_stuck` caches on the task: the moment the picture last changed, and the picture
# it compared against. Named here rather than spelled out at each use because `src/en/notify.py` reads the
# clock too, and an upstream rename that missed one of them would quietly stop the stuck toast, not fail.
CLOCK = "_last_change_time"
PICTURE = "_prev_frame_gray"
# Cleared as a pair: upstream re-seeds both only when the clock is missing, so dropping one and keeping the
# other would leave the two disagreeing about what was last seen.
CACHE = (CLOCK, PICTURE)

_patched = False


def forget(task):
    """Drop what the stuck detector remembers, so it seeds itself again on the next frame.

    Args:
        task: The mode about to start a run.
    """
    for name in CACHE:
        # Removed rather than blanked, because absence is what upstream tests for when it decides to re-seed.
        task.__dict__.pop(name, None)


def restarting(original_enable, task):
    """Wrap a mode's `enable` so starting a run starts its stuck clock too.

    Args:
        original_enable: The mode's own `enable`, which the Start button reaches through the run loop.
        task: The mode being wrapped.

    Returns:
        The replacement `enable`.
    """
    def enable():
        forget(task)
        original_enable()

    return enable


def apply():
    """Stop a run inheriting how long the screen looked frozen to the run before it."""
    global _patched
    if _patched:
        return

    try:
        from ok.task.task import BaseTask, TriggerTask
    except ImportError:
        logger.warning("could not import BaseTask, the stuck clock will carry over between runs")
        _patched = True
        return

    original_load_config = BaseTask.load_config

    def patched_load_config(self):
        # Wrapping here is what puts this ahead of the run loop, which takes its own reference to `enable`
        # when the mode moves to the Tasks tab. Only the modes have a stuck clock to start.
        if isinstance(self, TriggerTask):
            self.enable = restarting(self.enable, self)
        original_load_config(self)

    BaseTask.load_config = patched_load_config
    _patched = True
