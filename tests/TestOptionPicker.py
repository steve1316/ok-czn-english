"""Exercise the virtualized option picker against the real framework dialog.

`src/en/picker.py` rebinds three methods on ok-script's `ModifyListDialog`, so the things that can break are all
behavioural: a row failing to grey out, the search matching the wrong text, or Confirm handing back display text
instead of the canonical value the config stores. None of that shows up in a unit test of the patch's own
helpers, so these build the actual dialog offscreen and drive it.

Qt runs headless here through the offscreen platform plugin, which has to be chosen before `QApplication` exists.
"""

import os
import sys
import unittest
from html import escape
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyle, QWidget  # noqa: E402

from ok import og  # noqa: E402

from src.en import picker  # noqa: E402
from src.en.framework import import_ui  # noqa: E402
from src.en.game_data import CARDS  # noqa: E402
from src.en.game_text import DESCRIPTIONS  # noqa: E402
from src.en.overrides import ROUTE_NODES  # noqa: E402

ModifyListDialog = import_ui("tasks.ModifyListDialog", "ModifyListDialog")


class EchoApp:
    """Stands in for the running app's translator, which leaves English game names alone."""

    def tr(self, key):
        """Return the key untouched.

        Args:
            key: The string being translated.

        Returns:
            The same string.
        """
        return key


@unittest.skipIf(ModifyListDialog is None, "ok-script does not provide ModifyListDialog")
class TestOptionPicker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        og.app = EchoApp()
        # Called twice on purpose: the guard has to hold, or a second call would wrap the patch in itself.
        picker.apply()
        picker.apply()
        cls.parent = QWidget()

    def open_picker(self, options, selected=()):
        """Build a picker dialog the way a settings row does.

        Args:
            options: The roster to offer.
            selected: Values already saved in the setting.

        Returns:
            The `ModifyListDialog`.
        """
        return ModifyListDialog(list(selected), self.parent, options_available=options)

    def visible_rows(self, dialog):
        """Read the option rows the search box has left showing.

        Args:
            dialog: A picker built on a long roster.

        Returns:
            The text of every row still visible.
        """
        view = dialog.option_list
        return [view.item(row).text() for row in range(view.count()) if not view.isRowHidden(row)]

    def test_a_long_roster_builds_the_list_and_no_buttons(self):
        """One real PushButton per option is what makes the stock dialog take seconds to open."""
        dialog = self.open_picker(CARDS)
        self.assertEqual(len(CARDS), dialog.option_list.count())
        self.assertEqual({}, dialog.option_buttons)

    def test_a_short_roster_keeps_upstream_buttons(self):
        """Route Priority's four node types read better as buttons and cost nothing to build."""
        dialog = self.open_picker(ROUTE_NODES)
        self.assertIsNone(getattr(dialog, "option_list", None))
        self.assertEqual(len(ROUTE_NODES), len(dialog.option_buttons))

    def test_saved_values_start_greyed_out(self):
        """An option already held by the setting must not be addable a second time."""
        dialog = self.open_picker(CARDS, selected=[CARDS[5], CARDS[900]])
        view = dialog.option_list
        greyed = [view.item(row).text() for row in range(view.count())
                  if not view.item(row).flags() & Qt.ItemIsEnabled]
        self.assertEqual([CARDS[5], CARDS[900]], greyed)

    def test_adding_an_option_greys_it_out(self):
        dialog = self.open_picker(CARDS)
        dialog.add_available_item(CARDS[42])
        dialog.update_option_buttons()
        self.assertFalse(dialog.option_list.item(42).flags() & Qt.ItemIsEnabled)

    def test_search_keeps_only_the_matches(self):
        """The haystack is folded into a data role at build time, so a miss here means the wrong text was folded."""
        dialog = self.open_picker(CARDS)
        dialog.filter_available_options("sword")
        visible = self.visible_rows(dialog)
        self.assertTrue(visible, "the filter hid everything")
        for name in visible:
            self.assertIn("sword", name.casefold())

    def test_clearing_the_search_restores_every_row(self):
        dialog = self.open_picker(CARDS)
        dialog.filter_available_options("sword")
        dialog.filter_available_options("")
        self.assertEqual(len(CARDS), len(self.visible_rows(dialog)))

    def test_a_card_row_shows_its_effect(self):
        """The whole point of the tooltip: say what the card does, not just repeat the name."""
        dialog = self.open_picker(CARDS)
        described = next(row for row in range(dialog.option_list.count())
                         if dialog.option_list.item(row).text() in DESCRIPTIONS)
        item = dialog.option_list.item(described)
        self.assertIn(escape(DESCRIPTIONS[item.text()].splitlines()[0]), item.toolTip())

    def test_a_row_without_an_effect_shows_only_its_name(self):
        """Roughly 3% of cards have no description, and those must not render a dangling separator."""
        dialog = self.open_picker(CARDS)
        bare = next(row for row in range(dialog.option_list.count())
                    if dialog.option_list.item(row).text() not in DESCRIPTIONS)
        item = dialog.option_list.item(bare)
        self.assertEqual(f"<b>{escape(item.text())}</b>", item.toolTip())

    def test_tooltips_are_rich_text_so_qt_wraps_them(self):
        """Qt only word-wraps a tooltip it reads as rich text, and the longest effect is 196 characters."""
        dialog = self.open_picker(CARDS)
        self.assertTrue(dialog.option_list.item(0).toolTip().startswith("<b>"))

    def test_the_list_shows_tooltips_without_the_usual_delay(self):
        """Qt holds a tooltip back ~700ms, which is the whole wait when the tooltip is why you are hovering."""
        view = self.open_picker(CARDS).option_list
        self.assertEqual(0, view.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay, None, view))

    def test_only_the_option_list_loses_the_delay(self):
        """The style is set on the one view, so hovering anything else in the app behaves as it always did."""
        self.assertGreater(self.parent.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay, None, self.parent), 0)

    def test_the_list_keeps_its_fluent_styling(self):
        """A widget-level style can knock out a stylesheet, which would leave the list unthemed."""
        self.assertTrue(self.open_picker(CARDS).option_list.styleSheet())

    def test_saved_rows_carry_their_effect_on_the_selected_side(self):
        """Upstream fills that list inside `__init__`, so the rows are labelled from the update pass instead."""
        dialog = self.open_picker(CARDS, selected=["Absolute Zero"])
        item = dialog.list_widget.item(0)
        self.assertIn(escape(DESCRIPTIONS["Absolute Zero"].splitlines()[0]), item.toolTip())

    def test_a_newly_added_row_carries_its_effect_too(self):
        """Clicking an option appends a bare row, which only gets its tooltip on the pass that follows."""
        dialog = self.open_picker(CARDS)
        dialog.add_available_item("Rapid Slash")
        item = dialog.list_widget.item(dialog.list_widget.count() - 1)
        self.assertIn(escape(DESCRIPTIONS["Rapid Slash"]), item.toolTip())

    def test_both_lists_lose_the_tooltip_delay(self):
        dialog = self.open_picker(CARDS, selected=["Absolute Zero"])
        for name, view in (("available", dialog.option_list), ("selected", dialog.list_widget)):
            with self.subTest(list=name):
                self.assertEqual(0, view.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay, None, view))

    def option_row(self, dialog):
        """Find the layout holding the Available and Selected columns.

        Args:
            dialog: A picker built on a roster.

        Returns:
            The two-column layout, or None when the dialog has no roster and so no such row.
        """
        for index in range(dialog.viewLayout.count()):
            row = dialog.viewLayout.itemAt(index).layout()
            if row is not None and row.count() == 2 and all(row.itemAt(c).layout() is not None for c in range(2)):
                return row
        return None

    def test_the_two_option_columns_share_the_width_evenly(self):
        """Upstream splits the row 2:1, which leaves English card names cramped against a half-empty column."""
        for name, roster in (("cards", CARDS), ("route nodes", ROUTE_NODES)):
            with self.subTest(roster=name):
                row = self.option_row(self.open_picker(roster))
                self.assertEqual([1, 1], [row.stretch(0), row.stretch(1)])

    def test_a_free_text_list_has_no_columns_to_balance(self):
        """Without a roster the dialog is a single list, and its row must not be mistaken for the columns."""
        dialog = ModifyListDialog(["one", "two"], self.parent)
        self.assertIsNone(self.option_row(dialog))

    def test_confirm_returns_canonical_values_in_order(self):
        """The config stores the canonical value, so handing back display text would stop OCR matching."""
        dialog = self.open_picker(CARDS, selected=[CARDS[5]])
        dialog.add_available_item(CARDS[42])
        confirmed = []
        dialog.list_modified.connect(confirmed.extend)
        dialog.confirm()
        self.assertEqual([CARDS[5], CARDS[42]], confirmed)


if __name__ == "__main__":
    unittest.main()
