"""Give the settings rows enough width to read in English.

ok-script lays each settings row out as `[text column][stretch spacer][control]` but gives the text column no
stretch, so the spacer absorbs every spare pixel. Descriptions then wrap at their 220px minimum while most of
the row sits empty. That is tolerable in Chinese, which is dense enough to hide it, and unreadable in English.

Every patch here reaches into framework internals, so each one is written to fail quietly: if a future
ok-script release fixes the layout itself, the import or the lookup simply misses and nothing happens. Set
`OK_CZN_NO_LAYOUT_PATCH` to skip them all.
"""

import os

from ok import Logger

logger = Logger.get_logger(__name__)

# This repo runs ok-script-kes, whose UI lives under `ok.gui`. Upstream ok-script moved the same classes to
# `ok.ui.qt`, so try that first and fall back, which keeps the patch working across a future rebase.
UI_PACKAGES = ("ok.ui.qt", "ok.gui")
DISABLE_ENV = "OK_CZN_NO_LAYOUT_PATCH"
# Below this the view has not been laid out yet and `heightForWidth` returns a wildly inflated answer.
MIN_MEANINGFUL_WIDTH = 200

_patched = False


def _disabled():
    """Report whether the user has opted out of every layout patch.

    Returns:
        True when the escape-hatch environment variable is set.
    """
    if os.environ.get(DISABLE_ENV):
        logger.info(f"{DISABLE_ENV} set, leaving the stock layout alone")
        return True
    return False


def _import_ui(module, name):
    """Import one framework UI class from every package layout that provides it.

    Both package trees can be present at once, and only one of them is the live one. Rather than guess, patch
    every copy found: the unused tree is harmless, and this keeps working if a rebase swaps which is live.

    Args:
        module: Module path below the UI package, such as `tasks.LabelAndWidget`.
        name: Class name to pull out of it.

    Returns:
        A list of the classes found, empty when no installed layout provides it.
    """
    found = []
    for package in UI_PACKAGES:
        try:
            imported = __import__(f"{package}.{module}", fromlist=[name])
            found.append(getattr(imported, name))
        except (ImportError, AttributeError):
            continue
    if not found:
        logger.warning(f"could not import {module}.{name}, skipping that layout patch")
    return found


def widen_settings_text_column():
    """Let option labels and descriptions use the full width of a settings row.

    Removes the spacer that swallows the spare width and stretches the text column instead. Controls are
    unaffected because they set their own width through `control_width`.

    Must be paired with `size_cards_by_height_for_width`, otherwise cards keep reserving height for wrapping
    that no longer happens and leave a gap under their last row.
    """
    global _patched
    if _patched:
        return
    for label_and_widget in _import_ui("tasks.LabelAndWidget", "LabelAndWidget"):
        original_init = label_and_widget.__init__
        original_add_widget = label_and_widget.add_widget

        def patched_init(self, *args, _original=original_init, **kwargs):
            _original(self, *args, **kwargs)
            try:
                for index in reversed(range(self.layout.count())):
                    if self.layout.itemAt(index).spacerItem() is not None:
                        self.layout.takeAt(index)
                        break
                self.layout.setStretch(0, 1)
            except Exception as error:
                logger.warning(f"settings layout patch failed for this row: {error}")

        def patched_add_widget(self, widget, stretch=1, _original=original_add_widget):
            # Subclasses add their control after __init__ returns, most with the default stretch=1, which
            # would split the row evenly again and undo the widening. Controls size themselves already.
            _original(self, widget, 0)

        label_and_widget.__init__ = patched_init
        label_and_widget.add_widget = patched_add_widget
        _patched = True
    if _patched:
        logger.info("settings text column widened")


def _content_height(card):
    """Measure a card's content at the width it is actually laid out at.

    Word-wrapped labels report height through `heightForWidth` rather than `sizeHint`, so a layout holding
    them cannot describe its own height with `sizeHint` alone.

    Args:
        card: The `ExpandSettingCard` being measured.

    Returns:
        The content height in pixels, falling back to the size hint when no sensible width is known.
    """
    layout = card.viewLayout
    width = card.view.width()
    if width > MIN_MEANINGFUL_WIDTH and layout.hasHeightForWidth():
        height = layout.heightForWidth(width)
        if height > 0:
            return height
    return layout.sizeHint().height()


def size_cards_by_height_for_width():
    """Size expandable cards from real content height rather than the size hint.

    qfluentwidgets derives the expanded height from `viewLayout.sizeHint().height()`. Once the text column is
    widened that estimate no longer matches the laid-out height, so the card reserves space it never uses.
    """
    try:
        from qfluentwidgets import ExpandSettingCard
    except ImportError:
        logger.warning("could not import ExpandSettingCard, skipping height-for-width sizing")
        return

    def adjust_view_size(self):
        height = _content_height(self)
        self.spaceWidget.setFixedHeight(height)
        if self.isExpand:
            self.setFixedHeight(self.card.height() + height)

    def on_expand_value_changed(self):
        content = _content_height(self)
        top = self.viewportMargins().top()
        self.setFixedHeight(max(top + content - self.verticalScrollBar().value(), top))

    ExpandSettingCard._adjustViewSize = adjust_view_size
    ExpandSettingCard._onExpandValueChanged = on_expand_value_changed
    logger.info("expandable cards sized by height-for-width")


def align_card_action_buttons():
    """Keep a card's action buttons in one column down the list.

    A card header ends with `[buttons][spacing][expand chevron][spacing]`, and ok-script hides the chevron on
    cards with nothing to expand. Qt gives a hidden widget no space but keeps the spacers, so those rows push
    their buttons further right and the list gets a ragged edge. Reserving the hidden chevron's space fixes it.
    """
    for config_card in _import_ui("tasks.ConfigCard", "ConfigCard"):
        # Looked up separately because it is private: a rename should skip the patch, not raise out of startup.
        original_on_empty = getattr(config_card, "_on_empty_config_content", None)
        if original_on_empty is None:
            logger.warning("ConfigCard has no _on_empty_config_content, skipping button alignment")
            continue

        def patched_on_empty(self, _original=original_on_empty):
            try:
                button = self.card.expandButton
                policy = button.sizePolicy()
                policy.setRetainSizeWhenHidden(True)
                button.setSizePolicy(policy)
            except Exception as error:
                logger.warning(f"could not reserve expand button space: {error}")
            _original(self)

        config_card._on_empty_config_content = patched_on_empty
        logger.info("card action buttons aligned")


def translate_notifications():
    """Let toast notifications use the app translation catalog.

    `MainWindow.show_notification` only runs its text through Qt's own context, which holds the framework's
    strings. Everything this fork translates lives in the gettext catalog, so task names would otherwise reach
    the toast untranslated. A string with no catalog entry comes back unchanged.
    """
    for main_window in _import_ui("MainWindow", "MainWindow"):
        original_show = main_window.show_notification

        def patched_show(self, message, title=None, *args, _original=original_show, **kwargs):
            # ok-script has grown arguments here before, so forward the rest instead of respelling them.
            from ok import og

            try:
                if message:
                    message = og.app.tr(message)
                if title:
                    title = og.app.tr(title)
            except Exception as error:
                logger.warning(f"could not translate notification: {error}")
            _original(self, message, title, *args, **kwargs)

        main_window.show_notification = patched_show
        logger.info("notifications routed through the translation catalog")


def apply():
    """Apply every layout patch, unless the escape hatch is set.

    Note that ok-script-kes already carries its own collapsed-card height fix (`_sync_collapsed_height`), so
    the snap patch that ok-gf2-english needed is deliberately not ported here.
    """
    if _disabled():
        return
    widen_settings_text_column()
    size_cards_by_height_for_width()
    align_card_action_buttons()
    translate_notifications()
