"""Draw the Tasks page's list as a narrow column of mode names, each with the game's own icon.

Upstream's list is built for many scripts: a wide column, a description on every row, a monogram for a task with no icon, and a section titled
On-demand. With three modes, the descriptions repeat what the detail pane beside them already says and the title means nothing to a player.
"""

from pathlib import Path

from ok.ui.qt.kit.icons import load_icon, tinted_icon

from src.en.framework import import_ui

# Absolute, because a desktop shortcut can start the app from anywhere.
ICON_DIR = Path(__file__).resolve().parent.parent.parent / "icons" / "tasks"
# Which file in `ICON_DIR` each mode draws, by class name. A mode missing here keeps the framework's monogram.
ICON_FILES = {"ChaosMode": "chaos.svg", "SortieMode": "sortie.svg", "StoryMode": "story.svg"}
# The list column's width. Upstream's 372 px only pays off with a description on each row.
LIST_WIDTH = 260
# The one list section's title. This fork has no triggers for On-demand to contrast with.
SECTION_TITLES = {"On-demand": "Modes"}

_patched = False


def set_mode_icon(task):
    """Give a mode its icon, if it has a file, in a colour that follows the theme.

    Args:
        task: The mode, whose class name picks the file.
    """
    file_name = ICON_FILES.get(task.__class__.__name__)
    if file_name is not None:
        task.icon = tinted_icon(load_icon(ICON_DIR / file_name), "text")


def retitling(original):
    """Wrap the page's translation helper so its section title reads `SECTION_TITLES`.

    Args:
        original: The page module's `_t`.

    Returns:
        The replacement.
    """
    def translate(context, text):
        return original(context, SECTION_TITLES.get(text, text))

    return translate


def dropping_description(original):
    """Wrap `TaskRow.__init__` so a row shows only its name. The detail pane still shows the description.

    Args:
        original: The unbound `__init__` being replaced.

    Returns:
        The replacement.
    """
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        # The row re-elides this text on every resize.
        self._description = ""
        self.description_label.hide()

    return __init__


def apply():
    """Narrow the Tasks page's list and shorten its rows, before the window builds the page."""
    global _patched
    if _patched:
        return
    tasks_page = import_ui("tasks", "tasks_page")
    if tasks_page is None:
        return
    tasks_page.LIST_WIDTH = LIST_WIDTH
    tasks_page._t = retitling(tasks_page._t)
    tasks_page.TaskRow.__init__ = dropping_description(tasks_page.TaskRow.__init__)
    _patched = True
