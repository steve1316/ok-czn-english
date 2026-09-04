"""Make the option picker open instantly on the Global client's long rosters.

ok-script builds the "Available Options" pane of `ModifyListDialog` as one real `PushButton` per option, laid
out in a `FlowLayout`. Nothing is virtualized, so every button exists whether or not it is on screen. Upstream's
Chinese rosters are short enough for that to pass unnoticed. The Global client's are not: Cards to Remove offers
1,472 options, which costs about 1.25 seconds to open and, worse, about 0.75 seconds for every single keystroke
in the search box, because filtering calls `setVisible` on all 1,472 widgets.

Swapping the grid for a `ListWidget` in wrapped mode fixes both. `QListView` only creates delegates for the rows
actually on screen, so the same roster builds in about 4 ms and filters in about 3 ms, and wrapping keeps the
multi-column look rather than turning the pane into one very tall column.

Only the three methods that touch the option grid are replaced, and only when the roster is long. A short one -
Route Priority's four node types - falls straight through to upstream's buttons, and so does any failure, so the
worst case is the picker the user has today.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QListView, QListWidgetItem
from qfluentwidgets import ListWidget

from ok import Logger, og

from src.en.layout import import_ui

logger = Logger.get_logger(__name__)

# Data carried by each row: the canonical config value, and a pre-folded haystack the search box matches against.
# Folding once at build time keeps a keystroke to plain substring tests instead of 2,944 `casefold` calls.
OPTION_ROLE = Qt.UserRole
SEARCH_ROLE = Qt.UserRole + 1
# A row that can still be added. One already in Selected Options loses these flags and greys out.
ENABLED_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsSelectable
# Column sizing for the wrapped grid. The widest card name is over 550px, so the width is clamped and the view
# elides what does not fit - the full name stays available as a tooltip.
COLUMN_PADDING = 24
MIN_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 280
ROW_HEIGHT = 34

_patched = False


def wants_option_list(options, threshold):
    """Decide whether a roster is long enough to be worth virtualizing.

    Reuses the framework's own search-box threshold: a list long enough to need searching is long enough to need
    virtualizing, and that keeps the rule to one number rather than two that can drift apart.

    Args:
        options: The roster offered by the setting, or None for a free-text list.
        threshold: The framework's `SHOW_SEARCH_OPTIONS_THRESHOLD`.

    Returns:
        True when the virtualized list should replace the button grid.
    """
    return options is not None and len(options) > threshold


def build_option_list(dialog):
    """Build the virtualized replacement for one dialog's option grid.

    Args:
        dialog: The `ModifyListDialog` being set up.

    Returns:
        A `ListWidget` holding every available option.
    """
    view = ListWidget()
    view.setFlow(QListView.LeftToRight)
    view.setWrapping(True)
    view.setResizeMode(QListView.Adjust)
    # Every row is the same size, which lets the view work out its layout without measuring all of them.
    view.setUniformItemSizes(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    display_names = [og.app.tr(option) for option in dialog.options_available]
    metrics = view.fontMetrics()
    widest = max((metrics.horizontalAdvance(name) for name in display_names), default=0)
    size = QSize(max(MIN_COLUMN_WIDTH, min(widest + COLUMN_PADDING, MAX_COLUMN_WIDTH)), ROW_HEIGHT)

    for option, display in zip(dialog.options_available, display_names):
        item = QListWidgetItem(display)
        item.setData(OPTION_ROLE, option)
        item.setData(SEARCH_ROLE, f"{option}\n{display}".casefold())
        item.setSizeHint(size)
        item.setToolTip(display)
        view.addItem(item)

    view.itemClicked.connect(lambda item: dialog.add_available_item(item.data(OPTION_ROLE)))
    return view


def apply():
    """Replace the option grid with a virtualized list for every long roster."""
    global _patched
    if _patched:
        return
    dialog_class = import_ui("tasks.ModifyListDialog", "ModifyListDialog")
    threshold = import_ui("tasks.ModifyListDialog", "SHOW_SEARCH_OPTIONS_THRESHOLD")
    if dialog_class is None or threshold is None:
        return
    _patched = True

    original_create = dialog_class._create_available_options_widget
    original_update = dialog_class.update_option_buttons
    original_filter = dialog_class.filter_available_options

    def patched_create(self):
        if not wants_option_list(self.options_available, threshold):
            return original_create(self)
        try:
            self.option_list = build_option_list(self)
        except Exception as error:
            logger.warning(f"could not build the virtualized option list, falling back to buttons: {error}")
            return original_create(self)
        return self.option_list

    def patched_update(self):
        view = getattr(self, "option_list", None)
        if view is None:
            return original_update(self)
        # The rows already hold translated text, so compare against that rather than translating every option
        # again on every selection change.
        selected = {self.list_widget.item(row).text() for row in range(self.list_widget.count())}
        for row in range(view.count()):
            item = view.item(row)
            available = self.allow_duplication or item.text() not in selected
            item.setFlags(ENABLED_FLAGS if available else Qt.NoItemFlags)

    def patched_filter(self, text):
        view = getattr(self, "option_list", None)
        if view is None:
            return original_filter(self, text)
        keyword = text.strip().casefold()
        for row in range(view.count()):
            view.setRowHidden(row, bool(keyword) and keyword not in view.item(row).data(SEARCH_ROLE))

    dialog_class._create_available_options_widget = patched_create
    dialog_class.update_option_buttons = patched_update
    dialog_class.filter_available_options = patched_filter
    logger.info("long option lists virtualized")
