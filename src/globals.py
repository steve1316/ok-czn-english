from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        # Everything English-only lives under src/en/ so upstream's files stay untouched and merges stay clean.
        from src.en import layout, overrides, picker

        layout.apply()
        picker.apply()
        overrides.apply()
