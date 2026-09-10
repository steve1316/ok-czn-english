"""Give the game modes Start buttons, and drop the scaffold tabs.

Upstream ships the modes as trigger tasks, so the framework draws them as a switch in a separate Triggers tab.
"""

import time

from ok import Logger

from src.en.framework import import_ui

logger = Logger.get_logger(__name__)

# Upstream trigger tasks that are scaffolding or were never translated, hidden rather than deleted so that
# `ok_tasks/` stays byte-identical to upstream. Every other trigger task becomes a mode with a Start button,
# so a mode upstream renames or adds is picked up without editing a list here.
HIDDEN = ("TestTrigger", "GetMengbian")

_patched = False


def looping(task):
    """Wrap a trigger task's single-pass `run` so it repeats until the task stops.

    A trigger task's `run` handles one frame and returns. The executor is what called it again, cleared the
    cached frame in between, and paced it. A task in the one-time list is run once, so the loop does all three.

    Args:
        task: The mode being moved.

    Returns:
        The replacement `run`.
    """
    original_run = task.run
    original_enable = task.enable

    def run():
        # The Start button sets `_enabled` directly rather than calling `enable`, so the mode's own override
        # never runs. That override is what makes the three modes mutually exclusive and what resets the
        # per-run counters, without which a stop-after-N-rounds setting trips on the second Start.
        original_enable()
        while task.enabled:
            started = time.time()
            original_run()
            # A mode can stop itself, by reaching a round limit or the end of a story. Leaving the loop here
            # lets the executor finish the task properly instead of seeing it abandoned.
            if not task.enabled:
                break
            # Drops the cached frame so the next pass reads the current screen. This also raises once Stop is
            # pressed, which is the same exception the executor already handles for any other task.
            task.executor.reset_scene()
            # Upstream paced from the start of one pass to the start of the next. Sleeping the whole interval
            # on top of the pass would stretch every cycle by however long the pass took.
            # Read fresh each pass rather than captured once, so a handler can change the pace while the mode
            # runs - `src/en/observe.py` looks more often while a battle is on screen.
            remaining = task.trigger_interval - (time.time() - started)
            if remaining > 0:
                task.sleep(remaining)

    return run


def pausing(task, communicate):
    """Build the pause for a mode that now lives in the one-time list.

    `BaseTask.pause` pauses the whole executor for a trigger task, which is what makes the frame the mode
    reads block, and that is kept. What it does not do is record the pause on the task itself, and `TaskCard`
    reads `task.paused` to decide whether to offer Resume. `BaseTask.unpause` is already correct as it stands.

    Args:
        task: The mode being moved.
        communicate: The framework's signal hub, used to refresh the card.

    Returns:
        The replacement `pause`.
    """
    def pause():
        task.executor.pause()
        task._paused = True
        communicate.task.emit(task)

    return pause


def to_task(task, executor, communicate):
    """Move one mode from the Triggers tab to the Tasks tab.

    Args:
        task: The mode to move.
        executor: The task executor holding both lists.
        communicate: The framework's signal hub.
    """
    executor.trigger_tasks.remove(task)
    executor.onetime_tasks.append(task)
    task.run = looping(task)
    task.pause = pausing(task, communicate)
    # `TaskCard` offers an Edit button for anything loaded out of `ok_tasks/`, and it opens the Script tab,
    # which is gone. Clearing this drops the button. The cost is that the modes now count as built-in to the
    # debug file watcher, which only matters while editing `ok_tasks/` with the app running.
    task.is_custom = False
    # `on_create` restored this from the saved config. A run that ended in a crash leaves it set, and the
    # executor starts any enabled one-time task on its own, so a launch would silently resume the mode.
    task._enabled = False
    logger.info(f"{task.__class__.__name__} now starts from a button rather than a switch")


def restructure(executor, task_manager, communicate):
    """Re-shape the task lists before the window builds its tabs from them.

    Args:
        executor: The task executor holding both task lists.
        task_manager: The task manager, whose `has_custom` gates the Script and Templates tabs.
        communicate: The framework's signal hub.
    """
    # The Script and Templates tabs record and edit tasks, which this fork does not do. Turning off the
    # `custom_tasks` config cannot stand in for this, because that is also what makes the manager load
    # `ok_tasks/` in the first place.
    task_manager.has_custom = False

    # `get_all_tasks` hands back a fresh list, so moving tasks between the two underlying lists is safe.
    for task in executor.get_all_tasks():
        if task.__class__.__name__ in HIDDEN:
            task.visible = False
        elif task in executor.trigger_tasks:
            to_task(task, executor, communicate)


def apply():
    """Re-shape the task lists and tabs when the main window is built."""
    global _patched
    if _patched:
        return
    main_window = import_ui("MainWindow", "MainWindow")
    communicate = import_ui("Communicate", "communicate")
    if main_window is None or communicate is None:
        return
    original_init = main_window.__init__

    def patched_init(self, *args, **kwargs):
        from ok import og

        # The window reads both task lists to decide which tabs exist, so this has to run first. By now every
        # task is loaded and constructed, which is not true when this module is imported.
        try:
            restructure(og.executor, og.task_manager, communicate)
        except Exception as error:
            logger.warning(f"could not finish re-shaping the task list, the tabs may be half changed: {error}")
        original_init(self, *args, **kwargs)

    main_window.__init__ = patched_init
    _patched = True
