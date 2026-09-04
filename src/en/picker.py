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
equipment's own effect text from `game_text.py` rather than just repeating the name, on both sides of the
dialog, and shows it without the wait Qt normally puts in front of a tooltip.

Only the methods that touch the option pane are replaced, and the grid itself is only swapped out when the
roster is long. A short one - Route Priority's four node types - falls through to upstream's buttons, so
nothing changes where nothing was slow.

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
from PySide6.QtWidgets import QListWidgetItem, QProxyStyle, QStyle
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
# The dialog's two option columns, Available and Selected.
COLUMN_COUNT = 2

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


class InstantTooltipStyle(QProxyStyle):
    """Take the wait out of the option list's tooltips.

    Qt holds a tooltip back for about 700ms, which is a long pause when the tooltip is the reason you are
    hovering in the first place. That wait is a style hint rather than a setting, so overriding the hint is the
    supported way to change it. Everything else passes straight through to the real style, and this is set on
    the dialog's two lists alone, so no other tooltip in the app is affected.

    Showing the text directly instead, from the view's `entered` signal, does not work: the item's own tooltip
    still fires afterwards and the user gets two tooltips at once.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        """Answer one style question, cutting the tooltip delay to nothing.

        Args:
            hint: The style hint being asked about.
            option: Style option for the widget, when there is one.
            widget: The widget being styled.
            returnData: Out-parameter some hints use.

        Returns:
            The hint's value.
        """
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 0
        return super().styleHint(hint, option, widget, returnData)


def balance_dialog_columns(dialog):
    """Give Available Options and Selected Options an equal share of the dialog width.

    Upstream splits that row two to one. Its Chinese option names are short enough for the wider column to be
    worth it, but English card names are not, and the narrow side ends up holding a list plus its buttons in a
    third of the dialog. The split is set inside `__init__`, so it is corrected afterwards instead.

    The row is found by shape rather than by position: it is the only child of the view layout whose own two
    children are both layouts. The selected list's row looks similar but holds a widget and a layout, so this
    cannot pick it by mistake.

    Args:
        dialog: The `ModifyListDialog` being set up.
    """
    for index in range(dialog.viewLayout.count()):
        row = dialog.viewLayout.itemAt(index).layout()
        if row is None or row.count() != COLUMN_COUNT:
            continue
        if all(row.itemAt(column).layout() is not None for column in range(COLUMN_COUNT)):
            for column in range(COLUMN_COUNT):
                row.setStretch(column, 1)
            return


def use_instant_tooltips(view):
    """Take the tooltip delay off one view.

    Args:
        view: The view to restyle. Qt does not take ownership of a style, so the view holds the reference.
    """
    view.instant_tooltip_style = InstantTooltipStyle()
    view.setStyle(view.instant_tooltip_style)


def label_selected_rows(dialog):
    """Give the Selected Options rows the same tooltips as the options they were picked from.

    Upstream fills that list inside `__init__`, which this module deliberately leaves alone, so the rows are
    labelled from `update_option_buttons` instead. That runs once the list is populated and again after every
    add and remove, which is exactly when a row could be missing its tooltip. Reordering moves the item itself,
    so those rows keep theirs.

    Args:
        dialog: The `ModifyListDialog` being updated.
    """
    for row in range(dialog.list_widget.count()):
        item = dialog.list_widget.item(row)
        display = item.text()
        # The list stores display text, so go back through the dialog's own map for the name a description is
        # keyed by. On the Global client the two are the same, but a translated build would need the lookup.
        item.setToolTip(tooltip_for(dialog.source_by_display.get(display, display), display))


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
    use_instant_tooltips(view)
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
    original_wrap = dialog_class._wrap_dialog_buttons

    def virtualized(dialog):
        """Whether this dialog shows the list. All three patches route on this one rule."""
        return wants_option_list(dialog.options_available, threshold)

    def patched_create(self):
        if not virtualized(self):
            return original_create(self)
        self.option_list = build_option_list(self)
        # The Selected Options list already exists by now, and its rows want the same treatment.
        use_instant_tooltips(self.list_widget)
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
        label_selected_rows(self)

    def patched_filter(self, text):
        if not virtualized(self):
            return original_filter(self, text)
        keyword = text.strip().casefold()
        for row in range(self.option_list.count()):
            hidden = bool(keyword) and keyword not in self.option_list.item(row).data(SEARCH_ROLE)
            self.option_list.setRowHidden(row, hidden)

    def patched_wrap(self):
        original_wrap(self)
        # The last call `__init__` makes after installing the two-column row, so the row exists to rebalance.
        # Every dialog with a roster gets it, not only the virtualized ones, so the shape stays consistent.
        if self.options_available is not None:
            balance_dialog_columns(self)

    dialog_class._create_available_options_widget = patched_create
    dialog_class.update_option_buttons = patched_update
    dialog_class.filter_available_options = patched_filter
    dialog_class._wrap_dialog_buttons = patched_wrap
    logger.info("long option lists virtualized")
