"""Give every settings row the height it needs, move a list's value under its label, and hide the settings this fork has no use for.

Upstream's form top-aligns its layout, which packs rows at their size hints and cuts off a description that wraps further than its hint.
Its list rows reserve a wide column that a short value leaves mostly empty, and its Settings page offers CN messaging apps and its own MCP server.
"""

from PySide6.QtCore import Qt

from ok import Logger, og
from ok.util.GlobalConfig import (
    ENABLE_MCP_SERVER,
    NOTIFICATION_OPTION_NAME,
    QQ_BOT_NOTIFICATION_ENABLED,
    QQ_NOTIFICATION_ENABLED,
    WECHAT_NOTIFICATION_ENABLED,
    WECOM_NOTIFICATION_ENABLED,
    basic_options,
)

from src.en.framework import import_ui

logger = Logger.get_logger(__name__)

# The switches taken off the Settings page, by the section they sit in. A sub-setting only ever renders through its parent, so it goes too.
HIDDEN_SETTINGS = {
    NOTIFICATION_OPTION_NAME: (WECOM_NOTIFICATION_ENABLED, QQ_BOT_NOTIFICATION_ENABLED, QQ_NOTIFICATION_ENABLED, WECHAT_NOTIFICATION_ENABLED),
    basic_options.name: (ENABLE_MCP_SERVER,),
}

_patched = False


def fitting_rows(original):
    """Wrap `ConfigForm.add_buttons`, the form's last step before it measures itself, so each row gets its full height.

    Args:
        original: The unbound `add_buttons` being replaced.

    Returns:
        The replacement.
    """
    def add_buttons(self):
        # A box layout with an alignment caps each row at its size hint. A 750-character description in a 500 px form gets 207 of the 255 px it needs.
        self.viewLayout.setAlignment(Qt.AlignmentFlag(0))
        original(self)

    return add_buttons


def value_under_label(original):
    """Wrap `ListEditor.__init__` so the value sits under the row's text and the control column holds only the button.

    Args:
        original: The unbound `__init__` being replaced.

    Returns:
        The replacement.
    """
    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.control.layout().removeWidget(self.list_label)
        self._row_layout.itemAt(0).layout().addWidget(self.list_label)
        self.list_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        # `set_control` gave the holder a fixed width. With no minimum, the row's alignment shrinks it to the button.
        self.control.setMinimumWidth(0)
        self.update_value()

    return __init__


def hiding_an_empty_value(original):
    """Wrap `ListEditor.update_value` so an empty list leaves no blank line under the row's text.

    Args:
        original: The unbound `update_value` being replaced.

    Returns:
        The replacement.
    """
    def update_value(self):
        original(self)
        self.list_label.setVisible(bool(self.list_label.text()))

    return update_value


def hide_settings(global_config):
    """Take `HIDDEN_SETTINGS` off the Settings page and turn off any that were saved on, since nothing could turn them off afterwards.

    Args:
        global_config: The framework's global config, with its sections already registered.
    """
    for section, keys in HIDDEN_SETTINGS.items():
        option, saved = global_config.config_options[section], global_config.get_config(section)
        for key in keys:
            option.config_type.setdefault(key, {})["hidden"] = True
            if saved.get(key):
                saved[key] = False
                logger.info(f"turned off the hidden setting {key}")


def apply():
    """Patch the settings form, and hide the settings before the framework reads them to start its MCP server and build the page."""
    global _patched
    if _patched:
        return
    config_form = import_ui("tasks.config_form", "ConfigForm")
    if config_form is not None:
        config_form.add_buttons = fitting_rows(config_form.add_buttons)
    list_editor = import_ui("tasks.config_editors", "ListEditor")
    if list_editor is not None:
        list_editor.__init__ = value_under_label(list_editor.__init__)
        list_editor.update_value = hiding_an_empty_value(list_editor.update_value)
    hide_settings(og.global_config)
    _patched = True
