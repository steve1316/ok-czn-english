from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        # Everything English-only lives under src/en/ so upstream's files stay untouched and merges stay clean.
        from src.en import (  # noqa: E501
            battle, deck, desire, dialogue, dice, draft, equipment, events, layout, navigation,
            observe, ocr_text, overrides, persona, picker, pins, rewards, shell, shop, templates,
            notify, stuck, upload,
        )

        layout.apply()
        picker.apply()
        ocr_text.apply()
        templates.apply()
        # These edit the mode handler lists, so they must run after the task modules are importable.
        navigation.apply()
        events.apply()
        pins.apply()
        deck.apply()
        desire.apply()
        persona.apply()
        dice.apply()
        draft.apply()
        equipment.apply()
        # Anything wrapping a handler in `rewards.FILLED_IN` goes before rewards, which renames the
        # list entry it builds - after that rename, a later wrapper looking for the original name finds
        # nothing. Order does not otherwise matter: `handlers.wrap` composes rather than replaces.
        shop.apply()
        rewards.apply()
        battle.apply()
        observe.apply()
        dialogue.apply()
        overrides.apply()
        upload.apply()
        notify.apply()
        stuck.apply()
        # Re-shapes the task lists, so it hooks the window rather than the tasks.
        shell.apply()
