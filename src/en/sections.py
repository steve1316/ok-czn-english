"""Lay the mode settings out in the order a run meets them: the everyday ones flat on top, the rest under collapsible headers.

ok-script lays a card's settings out as one flat list in upstream's declaration order, so a switch and the rows it governs can
sit far apart. Its own `sub_configs` can hide rows, but only behind a saved switch that reads as turning the feature off. These
headers are display only, and each one counts its changed rows so a folded section still shows it was touched.
"""

from dataclasses import dataclass, field
from functools import partial

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ok import Logger, og
from ok.ui.qt.kit.buttons import Button
from ok.ui.qt.kit.labels import Label

from src.en import row_hints
from src.en.framework import import_ui
from src.en.etched_memory import ENTER_MEMORY_END, ETCHED_MEMORY, MEMORY_BONUS, MEMORY_CARD
from src.en.meditation import MEDITATE
from src.en.overrides import DESIRE_FACTION, DRAFTED_COMBATANT, EXTRACT_SPARE, FARMED_COMBATANT, HARDCORE, RISK_PICKS, SMART_CARD_PLAY, SORTIE_LEVEL
from src.en.reobserve import MODIFIER_BLACKLIST, REOBSERVE, SAVE_LIMIT_KEY
from src.en.rest import SHOP_SETTING
from src.en.shop import BUY_CARDS, PAID_THRESHOLD, TAKE_MONSTER_REWARDS
from src.en.zero_system import CODEX, CODEX_MERGE, CODEX_SEASON, MAX_MERGES

logger = Logger.get_logger(__name__)

# The settings shown first and never folded, in this order: the lead combatant and the loot claim, then the run, then the rest of
# the party, then what rerolls the Chaos start page. Chaos claims through the first loot key and Sortie through the second.
TOP = [FARMED_COMBATANT, DRAFTED_COMBATANT, "领取奖励(只使用验证卡)", "领取奖励", "几轮后停止(0为不停止)", "第几层boss前自动暂停", "只打第一层",
       "主战员优先级", "拉黑主战员", SORTIE_LEVEL, HARDCORE, RISK_PICKS,
       SAVE_LIMIT_KEY, REOBSERVE, MODIFIER_BLACKLIST, "刷初始卡牌", "刷空档"]
# Header title -> the settings folded under it, in the order they are shown. Both modes share the lists and a card draws only
# the keys it carries, so a section with none of them is not drawn. A key in neither list stays above everything.
SECTIONS = [
    ("Map", ["路线优先级", "任务优先级", "拉黑任务"]),
    ("Battle", [SMART_CARD_PLAY, "出牌优先级"]),
    ("Cards", ["获得卡牌优先级", "卡牌奖励优先级", TAKE_MONSTER_REWARDS, "移除卡牌列表", "复制卡牌列表", "闪光卡牌列表", "闪光优先级", "首层刷特定闪光",
               "生命值大于多少优先闪光(百分比)"]),
    ("Equipment", [EXTRACT_SPARE, "装备1号位优先级", "装备2号位优先级", "装备3号位优先级"]),
    ("Safe Zone", [SHOP_SETTING, BUY_CARDS, PAID_THRESHOLD, MEDITATE, "治疗崩溃"]),
    ("Saves", ["保留大于多少TB的存档"]),
    ("Season 3 - Persona", ["指定面具卡牌", "面具卡牌刻印"]),
    ("Season 4 - Desire", [DESIRE_FACTION]),
    ("Season 5 - Memory", [MEMORY_CARD, ETCHED_MEMORY, MEMORY_BONUS, ENTER_MEMORY_END]),
    ("Zero System", [CODEX, CODEX_SEASON, CODEX_MERGE, MAX_MERGES]),
]
# Every key placed by the lists above, in display order.
LAID_OUT = [*TOP, *(key for _, keys in SECTIONS for key in keys)]
# Shown in green after a header's title while some of its rows differ from their defaults. `{}` is how many.
CHANGED = "{} changed"
# Where a card keeps its built sections, as a list of `Section`.
SECTIONS_ATTR = "_en_sections"
# A header's chevron while its section is open and while it is folded.
OPEN_ICON, FOLDED_ICON = "chevron-down", "chevron-right"

_applied = False


@dataclass
class Section:
    """One header and the rows it folds away on a single card."""

    # The English title from `SECTIONS`.
    title: str
    # The row widget holding the button, placed directly above the first folded row.
    header: QWidget
    # The chevron button the user clicks, whose icon shows the open state.
    button: Button
    # The green count of changed rows beside the button, hidden while there are none.
    count: Label
    # The settings row widgets under this header, in display order.
    rows: list = field(default_factory=list)
    # Whether the rows are currently shown. Starts folded, and a kept form remembers it between mode switches.
    expanded: bool = False


def _build_header(title):
    """Build a header row with a chevron button that toggles its section and a count of its changed rows.

    Args:
        title: The English section title from `SECTIONS`, run through the app catalog for display.

    Returns:
        A `(header, button, count)` triple.
    """
    header = QWidget()
    layout = QHBoxLayout(header)
    # The button's own padding already spaces the count from the title.
    layout.setSpacing(0)
    button = Button(og.app.tr(title), FOLDED_ICON, "subtle")
    count = Label("", parent=header)
    count.setProperty("tone", "success")
    count.hide()
    layout.addWidget(button)
    layout.addWidget(count)
    layout.addStretch(1)
    return header, button, count


def _label(card, section):
    """Update a header's count of rows that differ from the mode's defaults.

    Args:
        card: The settings card holding the section.
        section: The `Section` whose count is updated.
    """
    changed = sum(1 for row in section.rows if row_hints.changed(card, row.key))
    section.count.setText(f"· {og.app.tr(CHANGED).format(changed)}")
    section.count.setVisible(bool(changed))


def on_change(card, *_):
    """Bring the header counts, Changed pills and greyed rows up to date after a value on the card changes.

    Args:
        card: The settings card whose row just changed.
    """
    for section in getattr(card, SECTIONS_ATTR, ()):
        _label(card, section)
    row_hints.refresh(card)
    card._adjust_config_content_size()


def _show_state(section):
    """Show or hide a section's rows and point its chevron to match `expanded`.

    Args:
        section: The `Section` to update.
    """
    section.button.set_icon(OPEN_ICON if section.expanded else FOLDED_ICON)
    for row in section.rows:
        row.setVisible(section.expanded)


def place_sections(card):
    """Put the `TOP` rows first and each section's header and rows last, then apply each section's open state.

    The trap is `__apply_sub_config_visibility`. Reset Config and any sub-config switch both
    run it, and it pulls every row out of the layout, puts them back from the top in `config_keys` order and shows
    them all. So `config_keys` is reordered to match, and the sections are re-placed and
    re-hidden every time it runs. A section keeps its open state across it.

    The caller re-measures the card afterwards, since both callers already do.

    Args:
        card: A settings card that has been laid out by `add_sections`.
    """
    layout = card.viewLayout
    top = [card.config_widget_by_key[key] for key in TOP if key in card.config_widget_by_key]
    indexes = [layout.indexOf(widget) for widget in card.config_widgets]
    start = min((index for index in indexes if index >= 0), default=0)
    for row in top:
        layout.removeWidget(row)
    for index, row in enumerate(top, start):
        layout.insertWidget(index, row)

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
        # Reset Config lands here without a value_changed, so the counts are rebuilt with the layout.
        _label(card, section)
    row_hints.refresh(card)


def add_sections(card):
    """Give a freshly built settings card its order, collapsible sections, Changed pills and greyed rows.

    Args:
        card: The card whose rows were just built, before it is measured.
    """
    laid_out = [key for key in LAID_OUT if key in card.config_widget_by_key]
    if not laid_out:
        return
    for key in laid_out:
        # Indented only under the row it needs, which the lists above place directly over it.
        rule = row_hints.RULES.get(key)
        card.config_widget_by_key[key].set_indent(rule is not None and rule.nested)
    # The framework's own re-sort follows `config_keys`, so the top rows lead it and the section rows trail it.
    top = [key for key in laid_out if key in TOP]
    rest = [key for key in card.config_keys if key not in laid_out]
    card.config_keys[:] = [*top, *rest, *laid_out[len(top):]]
    sections = []
    for title, keys in SECTIONS:
        present = [key for key in keys if key in card.config_widget_by_key]
        if not present:
            continue
        header, button, count = _build_header(title)
        section = Section(title, header, button, count, [card.config_widget_by_key[key] for key in present])
        button.clicked.connect(partial(toggle, card, section))
        sections.append(section)
    row_hints.decorate(card, laid_out)
    for row in card.config_widgets:
        if hasattr(row, "value_changed"):
            row.value_changed.connect(partial(on_change, card))
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
    """Hook the settings cards so every mode setting is laid out in run order."""
    global _applied
    if _applied:
        return
    form = import_ui("tasks.config_form", "ConfigForm")
    mixin = import_ui("tasks.config_form", "ConfigContentMixin")
    # Private and name-mangled, so looked up rather than referenced: a rename skips the patch instead of raising.
    original_apply_visibility = getattr(mixin, "_ConfigContentMixin__apply_sub_config_visibility", None)
    if form is None or original_apply_visibility is None:
        logger.warning("settings forms have changed shape, leaving the settings unfolded")
        return
    # On the form itself, which overrides the mixin's hook. The Settings page uses it too, and its keys match no list here.
    original_add_buttons = form.add_buttons

    def patched_add_buttons(self):
        # The last step before the card measures itself, so the folded rows are never measured as shown.
        try:
            add_sections(self)
        except Exception as error:
            logger.warning(f"could not fold the settings into sections: {error}")
        original_add_buttons(self)

    def patched_apply_visibility(self, *args):
        original_apply_visibility(self, *args)
        if not hasattr(self, SECTIONS_ATTR):
            return
        try:
            place_sections(self)
            self._adjust_config_content_size()
        except Exception as error:
            logger.warning(f"could not re-fold the settings sections: {error}")

    form.add_buttons = patched_add_buttons
    mixin._ConfigContentMixin__apply_sub_config_visibility = patched_apply_visibility
    _applied = True
    logger.info("settings folded into sections")
