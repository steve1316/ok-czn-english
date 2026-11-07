"""Give the game modes Start buttons, one usable at a time, drop the scaffold pages, and link About to this fork.

Upstream ships the modes as trigger tasks, so the framework draws them as switches in a separate Triggers section.
"""

import time

from ok import Logger, og

from src.en import task_list
from src.en.framework import import_ui

logger = Logger.get_logger(__name__)

# Upstream trigger tasks that are scaffolding or were never translated, hidden rather than deleted so that
# `ok_tasks/` stays byte-identical to upstream. Every other trigger task becomes a mode with a Start button,
# so a mode upstream renames or adds is picked up without editing a list here.
HIDDEN = ("TestTrigger", "GetMengbian")
# Upstream's entry in the About page's Other Projects grid, which the framework hardcodes rather than reading from `links`.
UPSTREAM_REPO = "https://github.com/baoxin1100/ok-kes"

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
    reads block, and that is kept. What it does not do is record the pause on the task itself, and the Tasks
    page reads `task.paused` to decide whether to offer Resume. `BaseTask.unpause` is already correct as it stands.

    Args:
        task: The mode being moved.
        communicate: The framework's signal hub, used to refresh the row.

    Returns:
        The replacement `pause`.
    """
    def pause():
        task.executor.pause()
        task._paused = True
        communicate.task.emit(task)

    return pause


def to_task(task, executor, communicate):
    """Move one mode from the page's Triggers section to its On-demand section.

    Args:
        task: The mode to move.
        executor: The task executor holding both lists.
        communicate: The framework's signal hub.
    """
    executor.trigger_tasks.remove(task)
    executor.onetime_tasks.append(task)
    task.run = looping(task)
    task.pause = pausing(task, communicate)
    # `TaskDetail` offers an Edit button for anything loaded out of `ok_tasks/`, and it opens the Script page,
    # which is gone. Clearing this drops the button. The cost is that the modes now count as built-in to the
    # debug file watcher, which only matters while editing `ok_tasks/` with the app running.
    task.is_custom = False
    task_list.set_mode_icon(task)
    # `on_create` restored this from the saved config. A run that ended in a crash leaves it set, and the
    # executor starts any enabled one-time task on its own, so a launch would silently resume the mode.
    task._enabled = False
    logger.info(f"{task.__class__.__name__} now starts from a button rather than a switch")


def lock_start(button, task, unlocked_tooltip):
    """Grey out a mode's Start while another mode holds the executor, and make sure it is clickable otherwise.

    Args:
        button: The row's action button or the detail pane's Run button.
        task: The mode `button` starts.
        unlocked_tooltip: The tooltip to show when `button` is not locked.
    """
    # A mode that is itself running or paused shows Stop or Resume here, and those must stay clickable.
    running = None if task.enabled else next((other for other in og.executor.onetime_tasks if other is not task and other.enabled), None)
    button.setEnabled(running is None)
    button.setToolTip(f"Stop {og.app.tr(running.name)} first" if running else unlocked_tooltip)


def locking_row(original):
    """Wrap `TaskRow.refresh` so no other mode can be started from the list while one is running.

    Args:
        original: The unbound `refresh` being replaced.

    Returns:
        The replacement.
    """
    def refresh(self):
        original(self)
        # Trigger rows have a switch and no button.
        if not self.is_trigger:
            # The framework has just set the button's own tooltip, so that is the one to keep when unlocked.
            lock_start(self.action_button, self.task, self.action_button.toolTip())

    return refresh


def locking_detail(original):
    """Wrap `TaskDetail.refresh` so no other mode can be started from its pane while one is running.

    Args:
        original: The unbound `refresh` being replaced.

    Returns:
        The replacement.
    """
    def refresh(self):
        original(self)
        # The pane starts with no task, and its Run button is hidden for a trigger task.
        if self.task is not None and not self.is_trigger:
            lock_start(self.run_button, self.task, "")

    return refresh


def redrawing_every_row(original):
    """Wrap `TasksPage._on_task_event` so every row redraws when any mode changes, which unlocks them at once.

    The framework redraws the changed row and leaves the rest to a timer that only runs while the page is on screen.

    Args:
        original: The unbound `_on_task_event` being replaced.

    Returns:
        The replacement, which drops the task because that is how the framework asks for every row.
    """
    def on_task_event(self, task=None):
        original(self)

    return on_task_event


def to_the_fork(original):
    """Wrap `ProjectCard.__init__` so the Chaos Zero Nightmare card opens this fork's repo, not upstream's.

    Args:
        original: The unbound `__init__` being replaced.

    Returns:
        The replacement.
    """
    def __init__(self, name, url, website=None, parent=None):
        if url == UPSTREAM_REPO:
            url, website = og.config["links"]["default"]["github"], None
        original(self, name, url, website, parent)

    return __init__


def restructure(executor, task_manager, communicate):
    """Re-shape the task lists before the window builds its pages from them.

    Args:
        executor: The task executor holding both task lists.
        task_manager: The task manager, whose `has_custom` gates the Script and Templates pages.
        communicate: The framework's signal hub.
    """
    # The Script and Templates pages record and edit tasks, which this fork does not do. Turning off the
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
    """Re-shape the task lists and pages when the main window is built."""
    global _patched
    if _patched:
        return
    main_window = import_ui("MainWindow", "MainWindow")
    communicate = import_ui("Communicate", "communicate")
    if main_window is None or communicate is None:
        return
    # Before the window is built, since the page connects its own bound methods as it is made.
    task_row = import_ui("tasks.tasks_page", "TaskRow")
    task_detail = import_ui("tasks.tasks_page", "TaskDetail")
    tasks_page = import_ui("tasks.tasks_page", "TasksPage")
    if task_row is not None and task_detail is not None and tasks_page is not None:
        task_row.refresh = locking_row(task_row.refresh)
        task_detail.refresh = locking_detail(task_detail.refresh)
        tasks_page._on_task_event = redrawing_every_row(tasks_page._on_task_event)
    project_card = import_ui("about.AboutTab", "ProjectCard")
    if project_card is not None:
        project_card.__init__ = to_the_fork(project_card.__init__)
    original_init = main_window.__init__

    def patched_init(self, *args, **kwargs):
        from ok import og

        # The window reads both task lists to decide which pages exist, so this has to run first. By now every
        # task is loaded and constructed, which is not true when this module is imported.
        try:
            restructure(og.executor, og.task_manager, communicate)
        except Exception as error:
            logger.warning(f"could not finish re-shaping the task list, the pages may be half changed: {error}")
        original_init(self, *args, **kwargs)

    main_window.__init__ = patched_init
    _patched = True
