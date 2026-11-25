"""Mark changed mode settings rows, grey out or narrow the ones another row governs, and hang trimmed text on an info icon.

ok-script can only hide a dependent row behind a saved switch, and shows no sign of which rows were moved off their defaults.
Here a dependent row stays in place but greyed, and a changed row carries a green pill. The one saved value touched is a narrowed
drop-down's, moved to its first choice once the choices no longer hold it.
"""

import operator
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QStyle, QWidget

from ok import og
from ok.ui.qt.kit.feedback import Pill
from ok.ui.qt.kit.icons import icon
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme

from src.en.etched_memory import ETCHED_MEMORY, MEMORY_BONUS, MEMORY_CARD
from src.en.overrides import EXTRACT_SPARE, TOOLTIPS
from src.en.reobserve import MODIFIER_BLACKLIST, REOBSERVE
from src.en.rest import SHOP_SETTING
from src.en.shop import BUY_CARDS, PAID_THRESHOLD, TAKE_MONSTER_REWARDS
from src.en.zero_system import CODEX, CODEX_SEASON, seasons_for

# The line shown under the Floor 1 Epiphany row while it cannot run. `{}` is the controlling row's label.
NEEDS_AN_ENTRY = "Needs an entry in {}."
# The pill after a changed row's title.
CHANGED = "Changed"
# How faint a greyed row is drawn. The app's QSS colours labels directly, so disabling alone barely shows.
GREYED_OPACITY = 0.4
# The kit icon drawn after a row's title when hovering it shows more, its theme colour, and its size in pixels.
TOOLTIP_ICON, TOOLTIP_ICON_COLOR, TOOLTIP_ICON_SIZE = "info", "text_secondary", 14
# The widest a tooltip's text runs before it wraps, in pixels.
TOOLTIP_MAX_WIDTH = 360
# How long the pointer may be off both the icon and its card before the card closes. Crossing the gap between them takes less.
CARD_GRACE_MS = 250
# The gap between the icon and the card opened below it, in pixels.
CARD_GAP = 6
# The card's look, copied from the stylesheet's `QToolTip` rule so it matches the app's other tooltips. Filled from the theme's tokens.
CARD_STYLE = "QLabel {{ color: {text}; background: {surface_alt}; border: 1px solid {border_strong}; border-radius: 6px; padding: 4px 8px; }}"
# Where a row keeps the widgets added to it: its title line, its Changed pill and its note.
TITLE_LINE_ATTR, PILL_ATTR, NOTE_ATTR = "_en_title_line", "_en_changed_pill", "_en_note"


@dataclass(frozen=True)
class Rule:
    """When one row idles another."""

    # The config key of the row whose value decides.
    controller: str
    # Takes the controller's saved value and says whether the dependent row cannot apply.
    idle: Callable
    # The line shown under the greyed row, or None for a row whose greying explains itself.
    note: Optional[str] = None

    @property
    def nested(self):
        """Whether the row needs its controller switched on or filled in, which is when it is indented under it."""
        return self.idle is operator.not_


# Dependent row key -> its `Rule`. Farm Starting Card is not greyed by Farm Gaps in return, so a config saved with both set
# still leaves one row the user can clear.
RULES = {
    BUY_CARDS: Rule(SHOP_SETTING, operator.not_),
    PAID_THRESHOLD: Rule(SHOP_SETTING, operator.not_),
    "装备1号位优先级": Rule(EXTRACT_SPARE, bool),
    "装备2号位优先级": Rule(EXTRACT_SPARE, bool),
    "装备3号位优先级": Rule(EXTRACT_SPARE, bool),
    MODIFIER_BLACKLIST: Rule(REOBSERVE, operator.not_),
    "刷空档": Rule("刷初始卡牌", bool),
    TAKE_MONSTER_REWARDS: Rule("卡牌奖励优先级", bool),
    # Upstream marks the Epiphany found only on a match with this list's first entry, so an empty list restarts every run.
    "首层刷特定闪光": Rule("闪光优先级", operator.not_, NEEDS_AN_ENTRY),
    ETCHED_MEMORY: Rule(MEMORY_CARD, bool),
    MEMORY_BONUS: Rule(MEMORY_CARD, bool),
}


@dataclass(frozen=True)
class Narrowing:
    """When one row decides which choices another row's drop-down offers."""

    # The config key of the row whose value decides.
    controller: str
    # Takes the controller's saved value and gives the choices, the one to fall back on first.
    options: Callable


# Dependent drop-down key -> its `Narrowing`.
NARROWED = {
    CODEX_SEASON: Narrowing(CODEX, seasons_for),
}


def wrapped(text, metrics, width):
    """Break text into lines no wider than `width`, splitting only between words.

    Args:
        text: The tooltip text, one paragraph.
        metrics: The `QFontMetrics` of the font the tooltip is drawn in.
        width: The widest a line may be, in pixels. A single word wider than this keeps a line to itself.

    Returns:
        The text with newlines where it wraps.
    """
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if line and metrics.horizontalAdvance(candidate) > width:
            lines.append(line)
            candidate = word
        line = candidate
    return "\n".join([*lines, line])


class HoverCard(QWidget):
    """The text an info icon holds, opened below it. It counts as part of the icon, so the pointer can move onto it."""

    def __init__(self, mark):
        # On the window rather than the icon, so a greyed row does not grey its card too.
        super().__init__(mark.window(), Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        # See-through, so the label's rounded corners show. A see-through window paints no stylesheet background of its own, so the
        # look sits on the label inside it.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # The icon that opened it, whose timers decide when it closes.
        self.mark = mark
        # Carries the text and the `CARD_STYLE` look.
        self.label = QLabel(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def enterEvent(self, event):
        self.mark.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.mark.hide_timer.start()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        self.mark.close_card()
        super().wheelEvent(event)


class InfoMark(QWidget):
    """The small info icon after a row's title, opening its text in a `HoverCard` while the pointer rests on it.

    Drawn here rather than as a Qt tooltip, which starts closing whenever the pointer crosses any widget's edge.
    """

    def __init__(self, text, parent=None):
        super().__init__(parent)
        # The full text, wrapped when the card opens.
        self.text = text
        self.icon = icon(TOOLTIP_ICON, TOOLTIP_ICON_COLOR)
        self.setFixedSize(TOOLTIP_ICON_SIZE, TOOLTIP_ICON_SIZE)
        # Built on first open and rebuilt if the icon moves to another window.
        self.card = None
        # Waits the same hover delay as a Qt tooltip before opening.
        self.show_timer = QTimer(self, singleShot=True, interval=self.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay))
        self.show_timer.timeout.connect(self.open_card)
        self.hide_timer = QTimer(self, singleShot=True, interval=CARD_GRACE_MS)
        self.hide_timer.timeout.connect(self.close_card)

    def paintEvent(self, event):
        self.icon.paint(QPainter(self), self.rect(), mode=QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled)

    def enterEvent(self, event):
        self.hide_timer.stop()
        if self.card is None or not self.card.isVisible():
            self.show_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.show_timer.stop()
        self.hide_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.close_card()
        super().mousePressEvent(event)

    def hideEvent(self, event):
        # A folded section or a page switch hides the icon without the pointer ever leaving it.
        self.close_card()
        super().hideEvent(event)

    def wheelEvent(self, event):
        # Scrolling slides the icon out from under the pointer, but Qt sends no Leave until the mouse moves. The base class ignores
        # the event, so the page still scrolls.
        self.close_card()
        super().wheelEvent(event)

    def open_card(self):
        """Open the card below the icon, styled for the current theme and kept on screen."""
        if self.card is None or self.card.parent() is not self.window():
            if self.card is not None:
                self.card.deleteLater()
            self.card = HoverCard(self)
        label = self.card.label
        label.setStyleSheet(CARD_STYLE.format(**theme.tokens()))
        label.ensurePolished()
        label.setText(wrapped(self.text, label.fontMetrics(), TOOLTIP_MAX_WIDTH))
        self.card.adjustSize()
        spot = self.mapToGlobal(QPoint(0, self.height() + CARD_GAP))
        screen = self.screen().availableGeometry()
        if spot.y() + self.card.height() > screen.bottom():
            spot.setY(self.mapToGlobal(QPoint(0, 0)).y() - CARD_GAP - self.card.height())
        spot.setX(max(screen.left(), min(spot.x(), screen.right() - self.card.width())))
        self.card.move(spot)
        self.card.show()

    def close_card(self):
        """Close the card and drop any open or close still pending."""
        self.show_timer.stop()
        self.hide_timer.stop()
        if self.card is not None:
            self.card.hide()



def changed(card, key):
    """Say whether a row's saved value differs from the mode's default.

    Args:
        card: The settings card holding the row.
        key: The row's config key.

    Returns:
        True when the value was moved off its default.
    """
    return card.config.get(key) != card.default_config.get(key)


def _column(row):
    """Return the text column a settings row keeps its title and description in.

    Args:
        row: A settings row.

    Returns:
        The column's `QVBoxLayout`.
    """
    return row.layout().itemAt(0).layout()


def _title_line(row):
    """Move a row's title into a line that can hold widgets after it, once.

    Args:
        row: A settings row whose title sits alone at the top of its text column.

    Returns:
        The title's `QHBoxLayout`. Widgets added go after the title, before the trailing stretch.
    """
    line = getattr(row, TITLE_LINE_ATTR, None)
    if line is None:
        column = _column(row)
        line = QHBoxLayout()
        line.setSpacing(6)
        column.removeWidget(row.title_label)
        column.insertLayout(0, line)
        # A wrapping label next to other widgets asks for a narrow width and wraps early. These titles fit on one line.
        row.title_label.setWordWrap(False)
        line.addWidget(row.title_label)
        line.addStretch(1)
        setattr(row, TITLE_LINE_ATTR, line)
    return line


def decorate(card, keys):
    """Give the named rows a hidden Changed pill and, where a description was trimmed, the info icon holding the rest.

    Args:
        card: A settings card whose rows were just built.
        keys: The config keys of the rows to decorate, the ones `sections.py` lays out.
    """
    for key in keys:
        row = card.config_widget_by_key.get(key)
        if row is None:
            continue
        line = _title_line(row)
        pill = Pill(og.app.tr(CHANGED), "success", row)
        pill.hide()
        for widget in (InfoMark(TOOLTIPS[key], row) if key in TOOLTIPS else None, pill):
            if widget is not None:
                line.insertWidget(line.count() - 1, widget, 0, Qt.AlignmentFlag.AlignVCenter)
        setattr(row, PILL_ATTR, pill)
        rule = RULES.get(key)
        if rule is not None and rule.note:
            note = Label("", "secondary", row, word_wrap=True)
            note.setMaximumWidth(row.description_label.maximumWidth())
            note.hide()
            column = _column(row)
            column.insertWidget(column.indexOf(row.description_label) + 1, note)
            setattr(row, NOTE_ATTR, note)


def narrow(row, options):
    """Offer only the given choices on a drop-down row, moving its saved value to the first one when they no longer hold it.

    Args:
        row: A drop-down settings row.
        options: The choices its controller allows, from its `Narrowing`.
    """
    if row.options != options:
        with QSignalBlocker(row.combo_box):
            row.combo_box.clear()
            row.combo_box.addItems([og.app.tr(option) for option in options])
        row.options = list(options)
    if row.config.get(row.key) not in options:
        # Through the row, so the move is saved and announced like a pick the user made.
        row.update_config(options[0])
    row.update_value()


def refresh(card):
    """Narrow each `NARROWED` drop-down, pill each row off its default, and grey out each row its `Rule` idles.

    Args:
        card: A settings card, re-checked after any of its values changes.
    """
    # First, so a value moved here is the one the pills and greying below are drawn from.
    for key, narrowing in NARROWED.items():
        row = card.config_widget_by_key.get(key)
        if row is not None and hasattr(row, "combo_box") and narrowing.controller in card.config_widget_by_key:
            narrow(row, narrowing.options(card.config.get(narrowing.controller)))
    for row in card.config_widgets:
        pill = getattr(row, PILL_ATTR, None)
        if pill is not None:
            pill.setVisible(changed(card, row.key))
    for key, rule in RULES.items():
        row = card.config_widget_by_key.get(key)
        if row is None or rule.controller not in card.config_widget_by_key:
            continue
        idle = bool(rule.idle(card.config.get(rule.controller)))
        note = getattr(row, NOTE_ATTR, None)
        if note is not None:
            note.setText(og.app.tr(rule.note).format(og.app.tr(rule.controller)))
            note.setVisible(idle)
        row.setEnabled(not idle)
        if row.graphicsEffect() is None:
            effect = QGraphicsOpacityEffect(row)
            effect.setOpacity(GREYED_OPACITY)
            row.setGraphicsEffect(effect)
        row.graphicsEffect().setEnabled(idle)
