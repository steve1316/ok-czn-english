"""The Auto Analysis switch on the Tasks tab, which turns on recording what the game's own Auto plays.

`observe.py` records Chaos battles for `scripts/study_auto.py`, at the cost of extra OCR on every battle frame and, with the burst
grabs, a second OCR engine. Upstream has no such recorder, so the fork keeps it off until this is on.
"""

from functools import cache

from ok import Logger
from ok.util.config import Config

from src.en.framework import import_ui

logger = Logger.get_logger(__name__)

# The switch's label, and the key it is saved under.
LABEL = "Auto Analysis"
# The line under the label.
DESCRIPTION = "Record what the game's Auto plays in Chaos battles, for offline study. Costs extra OCR on every battle frame."
# The file under `configs/` the switch is saved to.
CONFIG_NAME = "auto_analysis"
# Where a tab keeps its heading and switch card, so a rebuilt card list reuses them rather than adding a second pair.
SWITCH = "_en_auto_analysis"
# The heading that sets the switch apart from the modes above it.
HEADING = "Options"

_patched = False


# Read from disk on first use rather than at import, so importing this never writes a config file.
@cache
def setting():
    """Load the saved switch once.

    Returns:
        The `Config` holding `LABEL`, off by default.
    """
    return Config(CONFIG_NAME, {LABEL: False})


def enabled():
    """Say whether Auto Analysis is switched on.

    Returns:
        True once the switch on the Tasks tab is on.
    """
    return bool(setting().get(LABEL))


def switch_card(parent):
    """Build the card that holds the switch, styled like a trigger task's.

    Args:
        parent: The Tasks tab's card list the card goes in.

    Returns:
        The card, showing the saved state.
    """
    from PySide6.QtCore import Qt
    from qfluentwidgets import FluentIcon, SettingCard, SwitchButton

    card = SettingCard(FluentIcon.SEARCH, LABEL, DESCRIPTION, parent)
    # The mode cards above it have no icon. The spacing that followed the icon becomes the left margin, lining the title up with theirs.
    card.iconLabel.hide()
    card.hBoxLayout.setContentsMargins(0, 0, 0, 0)
    switch = SwitchButton(parent=card)
    switch.setOnText("Enabled")
    switch.setOffText("Disabled")
    switch.setChecked(enabled())
    # `Config` saves itself on every set.
    switch.checkedChanged.connect(lambda checked: setting().__setitem__(LABEL, checked))
    card.hBoxLayout.addWidget(switch, 0, Qt.AlignRight)
    card.hBoxLayout.addSpacing(16)
    return card


def heading(parent):
    """Build the label that sits between the last mode and the switch.

    Args:
        parent: The Tasks tab's card list the label goes in.

    Returns:
        The label, given a fixed height because the card list stacks its children by their current height.
    """
    from PySide6.QtCore import Qt
    from qfluentwidgets import StrongBodyLabel

    label = StrongBodyLabel(HEADING, parent)
    label.setFixedHeight(32)
    label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
    return label


def apply():
    """Put the switch on the Tasks tab, below the last mode."""
    global _patched
    if _patched:
        return
    tab = import_ui("tasks.OneTimeTaskTab", "OneTimeTaskTab")
    if tab is None:
        return
    original_refresh = tab.refresh_ui

    def patched_refresh(self):
        original_refresh(self)
        # Group tabs hold imported scripts, so only the main Tasks tab gets it.
        if not self.is_standalone:
            return
        try:
            widgets = getattr(self, SWITCH, None)
            if widgets is None:
                widgets = (heading(self.task_cards_view), switch_card(self.task_cards_view))
                setattr(self, SWITCH, widgets)
            else:
                for widget in widgets:
                    self.remove_task_card(widget)
            # In the mode cards' own list, last, so it sits below Semi-Auto Story Mode with their spacing and width.
            for widget in widgets:
                self.add_task_card(widget)
        except Exception as error:
            logger.warning(f"could not add the {LABEL} switch: {error}")

    tab.refresh_ui = patched_refresh
    _patched = True
