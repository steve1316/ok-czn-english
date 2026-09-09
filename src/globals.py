from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        # Everything English-only lives under src/en/ so upstream's files stay untouched and merges stay clean.
        from src.en import (  # noqa: E501
            battle, dialogue, dice, draft, events, layout, navigation, observe, ocr_text, overrides,
            picker, rewards, shell, shop, templates, notify, upload,
        )

        layout.apply()
        picker.apply()
        ocr_text.apply()
        templates.apply()
        # These edit the mode handler lists, so they must run after the task modules are importable.
        navigation.apply()
        events.apply()
        dice.apply()
        draft.apply()
        # Before rewards, which wraps `handle_shop` by reading it back off the module, so this one has
        # to be in place first for both to survive.
        shop.apply()
        rewards.apply()
        battle.apply()
        observe.apply()
        dialogue.apply()
        overrides.apply()
        upload.apply()
        notify.apply()
        # Re-shapes the task lists, so it hooks the window rather than the tasks.
        shell.apply()
