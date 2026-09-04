"""Make the option picker open instantly on the Global client's long rosters.

ok-script builds the "Available Options" pane of `ModifyListDialog` as one real `PushButton` per option, laid
out in a `FlowLayout`. Nothing is virtualized, so every button exists whether or not it is on screen. Upstream's
Chinese rosters are short enough for that to pass unnoticed. The Global client's are not: Cards to Remove offers
1,472 options, which costs about 2.6 seconds to open the dialog and another 2.9 on the first search keystroke,
because filtering calls `setVisible` on all 1,472 widgets.

Swapping the grid for a `ListWidget` fixes both. `QListView` only builds delegates for the rows actually on
screen, so the same roster is ready in about 2 ms and filters in about 3 ms, and every row spans the full width
of the pane, which a grid of fixed-width buttons never did.

Building the rows here is also what makes a useful tooltip possible, so each one carries the card's or the
equipment's own effect text from `game_text.py` rather than just repeating the name, and shows it on hover
instead of after Qt's usual delay.

Only the three methods that touch the option grid are replaced, and only when the roster is long. A short one -
Route Priority's four node types - falls through to upstream's buttons, so nothing changes where nothing was
slow.

The virtualization half of this is not really about the English client. It works around a framework performance
bug that only happens to bite at Global-client roster sizes, so it belongs in ok-script's own `ModifyListDialog`
and should go once a release carries the fix. The tooltips are fork-local and stay either way.

One thing is knowingly given up: upstream wires touch drag-scrolling to the `QScrollArea` the list now sits in,
and that outer area no longer scrolls. The framework's helper cannot be pointed at the list instead, because it
calls `.widget()`, which a `QListWidget` does not have. The wheel and the scrollbar both work, and the Selected
Options list beside it has never had touch scrolling either.
"""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QListWidgetItem, QToolTip
from qfluentwidgets import ListWidget

from ok import Logger, og

from src.en.framework import import_ui
from src.en.game_text import DESCRIPTIONS

logger = Logger.get_logger(__name__)

# Data carried by each row: the canonical config value, and a pre-folded haystack the search box matches against.
# Folding once at build time keeps a keystroke to plain substring tests instead of 2,944 `casefold` calls.
OPTION_ROLE = Qt.UserRole
SEARCH_ROLE = Qt.UserRole + 1
# A row that can still be added. One already in Selected Options loses these flags and greys out.
ENABLED_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsSelectable
# Used only if the framework's own `SHOW_SEARCH_OPTIONS_THRESHOLD` cannot be found, which would otherwise hand
# every roster back to the slow grid. It matches that constant's value today, and a test asserts it resolves.
FALLBACK_THRESHOLD = 20

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


def tooltip_for(option, display):
    """Build the hover text for one option.

    The result is HTML rather than plain text on purpose. Qt only word-wraps a tooltip it recognises as rich
    text, and the longest card effect is 196 characters, which would otherwise be drawn as one 1,440px line.
    Names and effects both contain characters HTML would eat, so both are escaped.

    Args:
        option: The canonical config value, which is the name the description is keyed by.
        display: The translated name shown on the row.

    Returns:
        The name, followed by its effect text when the game data has one.
    """
    name = f"<b>{escape(display)}</b>"
    effect = DESCRIPTIONS.get(option)
    if not effect:
        return name
    return f"{name}<br><br>{escape(effect).replace(chr(10), '<br>')}"


def show_row_tooltip(view, index):
    """Put a row's tooltip up as soon as the cursor reaches it.

    Qt waits about 700ms before showing a tooltip, which is a long pause when the tooltip is the reason you are
    hovering in the first place. The delay is a style hint rather than a setting, so the way to skip it is to
    show the text directly. Passing the row's rectangle lets Qt hide it again on the way out, and the next row
    replaces it.

    Args:
        view: The option list.
        index: Model index of the row now under the cursor.
    """
    item = view.itemFromIndex(index)
    if item is not None:
        QToolTip.showText(QCursor.pos(), item.toolTip(), view, view.visualRect(index))


def build_option_list(dialog):
    """Build the virtualized replacement for one dialog's option grid.

    Args:
        dialog: The `ModifyListDialog` being set up.

    Returns:
        A `ListWidget` holding every available option.
    """
    view = ListWidget()
    # Every row is the same size, so the view lays itself out from the first one rather than measuring all of
    # them. Rows then span the pane, and a name too long for it elides with the full text left in the tooltip.
    view.setUniformItemSizes(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    for option in dialog.options_available:
        display = og.app.tr(option)
        item = QListWidgetItem(display)
        item.setData(OPTION_ROLE, option)
        item.setData(SEARCH_ROLE, f"{option}\n{display}".casefold())
        item.setToolTip(tooltip_for(option, display))
        view.addItem(item)

    view.itemClicked.connect(lambda item: dialog.add_available_item(item.data(OPTION_ROLE)))
    view.entered.connect(lambda index: show_row_tooltip(view, index))
    return view


def apply():
    """Replace the option grid with a virtualized list for every long roster."""
    global _patched
    if _patched:
        return
    dialog_class = import_ui("tasks.ModifyListDialog", "ModifyListDialog")
    if dialog_class is None:
        return
    # The dialog is the hard dependency. The threshold only decides which rosters qualify, so a rename there
    # must not cost the user the whole fix.
    threshold = import_ui("tasks.ModifyListDialog", "SHOW_SEARCH_OPTIONS_THRESHOLD")
    if threshold is None:
        threshold = FALLBACK_THRESHOLD
    _patched = True

    original_create = dialog_class._create_available_options_widget
    original_update = dialog_class.update_option_buttons
    original_filter = dialog_class.filter_available_options

    def virtualized(dialog):
        """Whether this dialog shows the list. All three patches route on this one rule."""
        return wants_option_list(dialog.options_available, threshold)

    def patched_create(self):
        if not virtualized(self):
            return original_create(self)
        self.option_list = build_option_list(self)
        return self.option_list

    def patched_update(self):
        if not virtualized(self):
            return original_update(self)
        # The rows already hold translated text, so compare against that rather than translating every option
        # again on every selection change.
        selected = {self.list_widget.item(row).text() for row in range(self.list_widget.count())}
        for row in range(self.option_list.count()):
            item = self.option_list.item(row)
            available = self.allow_duplication or item.text() not in selected
            item.setFlags(ENABLED_FLAGS if available else Qt.NoItemFlags)

    def patched_filter(self, text):
        if not virtualized(self):
            return original_filter(self, text)
        keyword = text.strip().casefold()
        for row in range(self.option_list.count()):
            hidden = bool(keyword) and keyword not in self.option_list.item(row).data(SEARCH_ROLE)
            self.option_list.setRowHidden(row, hidden)

    dialog_class._create_available_options_widget = patched_create
    dialog_class.update_option_buttons = patched_update
    dialog_class.filter_available_options = patched_filter
    logger.info("long option lists virtualized")
