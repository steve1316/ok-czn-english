"""Keep each mode's settings form instead of rebuilding it on every switch.

Upstream's Tasks page destroys the open form and builds the next from scratch each time a mode is selected. That restyles every row, so switching
between modes with long forms visibly lags. It also forgets which seasonal sections were open.
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from src.en.framework import import_ui

_patched = False


def holding_forms(original):
    """Wrap `TaskDetail.__init__` so its scroll area keeps one holder, with every form built so far inside it.

    Args:
        original: The unbound `__init__` being replaced.

    Returns:
        The replacement.
    """
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        holder = QWidget()
        # The name the framework's stylesheet makes a scroll area's contents transparent by.
        holder.setObjectName("scrollContents")
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        self.form_scroll.setWidget(holder)

        def show_form(form):
            # Moving a form between parents would restyle it, so it only moves the first time.
            if form.parentWidget() is not holder:
                column.addWidget(form)
            form.show()
            self.form_scroll.verticalScrollBar().setValue(0)

        # `show_task` hands every form to this, and the real one would delete whatever it replaces.
        self.form_scroll.setWidget = show_form

    return __init__


def keeping_the_open_form(original):
    """Wrap `TaskDetail.show_task` so it finds no form to delete, only a hidden one left for later.

    Args:
        original: The unbound `show_task` being replaced.

    Returns:
        The replacement.
    """
    def show_task(self, task, is_trigger):
        if self.form is not None:
            self.form.hide()
            self.form = None
        original(self, task, is_trigger)

    return show_task


def reusing_forms(config_form):
    """Wrap the page's `ConfigForm` so each task builds its form once.

    Args:
        config_form: The form class the page builds from.

    Returns:
        A function the page can call in place of the class.
    """
    forms = {}

    def form_for(task, *args):
        if task in forms:
            # A task or the remote control may have changed the config while this form was hidden.
            forms[task].update_config()
        else:
            forms[task] = config_form(task, *args)
        return forms[task]

    return form_for


def apply():
    """Make the Tasks page keep its forms."""
    global _patched
    if _patched:
        return
    tasks_page = import_ui("tasks", "tasks_page")
    if tasks_page is None:
        return
    tasks_page.TaskDetail.__init__ = holding_forms(tasks_page.TaskDetail.__init__)
    tasks_page.TaskDetail.show_task = keeping_the_open_form(tasks_page.TaskDetail.show_task)
    tasks_page.ConfigForm = reusing_forms(tasks_page.ConfigForm)
    _patched = True
