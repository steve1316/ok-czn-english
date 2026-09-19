"""Fold each season's settings behind a collapsible header on the mode settings cards.

ok-script lays a card's settings out as one flat list, so the Persona settings from Season 3 and the Desire
setting from Season 4 sit among the everyday ones. Its own `sub_configs` can hide rows, but only behind a saved
switch that reads as turning the feature off, which it does not. These headers are display only.
"""

from dataclasses import dataclass, field
from functools import partial

from PySide6.QtCore import QMargins
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon, TransparentPushButton

from ok import Logger, og

from src.en.framework import import_ui
from src.en.overrides import DESIRE_FACTION

logger = Logger.get_logger(__name__)

# Header title -> the settings folded under it, in the order they are shown. A section whose keys a card does not
# carry is simply not drawn, so Sortie gets neither.
SECTIONS = [
    ("Season 3 - Persona", ["指定面具卡牌", "面具卡牌刻印"]),
    ("Season 4 - Desire", [DESIRE_FACTION]),
]
# Where a card keeps its built sections, as a list of `Section`.
SECTIONS_ATTR = "_en_sections"

# ok-script's row styling and sub-config indent, resolved once in `apply`.
_configure_row = None
_indent = 0
_applied = False


@dataclass
class Section:
    """One header and the rows it folds away on a single card."""

    # The row widget holding the button, placed directly above the first folded row.
    header: QWidget
    # The chevron button the user clicks, whose icon shows the open state.
    button: TransparentPushButton
    # The settings row widgets under this header, in display order.
    rows: list = field(default_factory=list)
    # Whether the rows are currently shown. Always starts collapsed.
    expanded: bool = False


def _build_header(title):
    """Build a header row with a chevron button that toggles its section.

    Args:
        title: The English section title from `SECTIONS`, run through the app catalog for display.

    Returns:
        A `(header, button)` pair.
    """
    header = QWidget()
    layout = QHBoxLayout(header)
    if _configure_row is not None:
        _configure_row(header, layout)
    button = TransparentPushButton(FluentIcon.CHEVRON_RIGHT, og.app.tr(title))
    layout.addWidget(button)
    layout.addStretch(1)
    return header, button


def _show_state(section):
    """Show or hide a section's rows and point its chevron to match `expanded`.

    Args:
        section: The `Section` to update.
    """
    section.button.setIcon(FluentIcon.CHEVRON_DOWN_MED if section.expanded else FluentIcon.CHEVRON_RIGHT)
    for row in section.rows:
        row.setVisible(section.expanded)


def place_sections(card):
    """Put each section's header and rows below the card's other settings and apply its open state.

    The trap is `__apply_sub_config_visibility`. Reset Config, a config-code import and any sub-config switch all
    run it, and it pulls every row out of the layout, puts them back from the top in `config_keys` order and shows
    them all. So the section rows are moved to the end of `config_keys`, and the sections are re-placed and
    re-hidden every time it runs. Open state is not remembered, so every card starts with its sections collapsed.

    The caller re-measures the card afterwards, since both callers already do.

    Args:
        card: A settings card that has been given sections by `add_sections`.
    """
    layout = card.viewLayout
    folded = set()
    for section in getattr(card, SECTIONS_ATTR, ()):
        folded.update(section.rows)
        layout.removeWidget(section.header)
        for row in section.rows:
            layout.removeWidget(row)

    index = max((layout.indexOf(widget) for widget in card.config_widgets if widget not in folded), default=-1) + 1
    for section in getattr(card, SECTIONS_ATTR, ()):
        for widget in (section.header, *section.rows):
            layout.insertWidget(index, widget)
            index += 1
        _show_state(section)


def add_sections(card):
    """Give a freshly built settings card its collapsible sections.

    Args:
        card: The card whose rows were just built, before its Operation row is added and it is measured.
    """
    sections = []
    for title, keys in SECTIONS:
        present = [key for key in keys if key in card.config_widget_by_key]
        if not present:
            continue
        header, button = _build_header(title)
        section = Section(header, button)
        for key in present:
            # Moved to the end so the framework's own re-sort keeps them together at the bottom.
            card.config_keys.remove(key)
            card.config_keys.append(key)
            row = card.config_widget_by_key[key]
            row.layout.setContentsMargins(row.layout.contentsMargins() + QMargins(_indent, 0, 0, 0))
            section.rows.append(row)
        button.clicked.connect(partial(toggle, card, section))
        sections.append(section)
    if sections:
        setattr(card, SECTIONS_ATTR, sections)
        place_sections(card)


def toggle(card, section, *_):
    """Open a collapsed section or collapse an open one.

    Args:
        card: The card holding the section.
        section: The `Section` whose header was clicked.
    """
    section.expanded = not section.expanded
    _show_state(section)
    card._adjust_config_content_size()


def apply():
    """Hook the settings cards so seasonal settings are built into collapsible sections."""
    global _applied, _configure_row, _indent
    if _applied:
        return
    mixin = import_ui("tasks.ConfigCard", "ConfigContentMixin")
    # Private and name-mangled, so looked up rather than referenced: a rename skips the patch instead of raising.
    original_apply_visibility = getattr(mixin, "_ConfigContentMixin__apply_sub_config_visibility", None)
    if mixin is None or original_apply_visibility is None:
        logger.warning("settings cards have changed shape, leaving seasonal settings unfolded")
        return
    _configure_row = import_ui("common.design_system", "configure_row")
    _indent = getattr(import_ui("common.design_system", "DesignToken"), "SUBCONFIG_INDENT", 0)
    original_add_buttons = mixin.add_buttons

    def patched_add_buttons(self):
        # The last step before the card measures itself, so the folded rows are never measured as shown.
        try:
            add_sections(self)
        except Exception as error:
            logger.warning(f"could not fold seasonal settings: {error}")
        original_add_buttons(self)

    def patched_apply_visibility(self, *args):
        original_apply_visibility(self, *args)
        if not getattr(self, SECTIONS_ATTR, None):
            return
        try:
            place_sections(self)
            self._adjust_config_content_size()
        except Exception as error:
            logger.warning(f"could not re-fold seasonal settings: {error}")

    mixin.add_buttons = patched_add_buttons
    mixin._ConfigContentMixin__apply_sub_config_visibility = patched_apply_visibility
    _applied = True
    logger.info("seasonal settings folded into sections")
