"""Apply every `src/en/` patch, in an order that matters.

This is the only place the fork's modules are wired in. Each `apply()` below is commented where its position
in the sequence is load-bearing, and the rest may be reordered freely.
"""

from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        # Everything English-only lives under src/en/ so upstream's files stay untouched and merges stay clean.
        from src.en import (  # noqa: E501
            battle, claims, dashboard, deck, desire, devices, dialogue, dice, draft, enter, equipment, etched_memory, events, frame_log, layout,
            log_text, memory_limit, monitors, navigation, observe, ocr_text, overrides, persona, picker, pins, remote, rest, rewards, sections,
            shell, shop, shutdown, templates, notify, stuck, upload,
        )

        # Neither does anything outside a debug run, and nothing else depends on when they start.
        frame_log.apply()
        remote.apply()
        layout.apply()
        sections.apply()
        picker.apply()
        ocr_text.apply()
        # Before log_text, so its translation wraps this ordering and the keys arrive here already in English.
        dashboard.apply()
        log_text.apply()
        templates.apply()
        # These edit the mode handler lists, so they must run after the task modules are importable.
        navigation.apply()
        events.apply()
        enter.apply()
        pins.apply()
        deck.apply()
        desire.apply()
        etched_memory.apply()
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
        rest.apply()
        memory_limit.apply()
        shutdown.apply()
        devices.apply()
        monitors.apply()
        # Last of the handler-list edits, so it wraps the lists every other module has finished shaping.
        claims.apply()
        # Re-shapes the task lists, so it hooks the window rather than the tasks.
        shell.apply()
