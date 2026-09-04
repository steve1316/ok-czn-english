"""Resolve framework classes across the two ok-script package layouts.

Every patch module under `src/en/` reaches into ok-script internals, and the classes it needs sit in a different
package depending on which release is installed. Looking them up through here keeps that one detail in one
place, and keeps a missing class a skipped patch rather than a crash on startup.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# This repo runs ok-script-kes, whose live UI is `ok.gui`. Upstream ok-script moved the same classes to
# `ok.ui.qt`, so fall back to that and the patches survive a future rebase. The first hit wins: both trees can
# be installed at once, and importing the unused one would only pull a second copy of the widgets into memory.
UI_PACKAGES = ("ok.gui", "ok.ui.qt")


def import_ui(module, name):
    """Import one framework UI attribute from whichever package layout is installed.

    Args:
        module: Module path below the UI package, such as `tasks.LabelAndWidget`.
        name: Class or constant to pull out of it.

    Returns:
        The attribute, or None when no installed layout provides it.
    """
    for package in UI_PACKAGES:
        try:
            imported = __import__(f"{package}.{module}", fromlist=[name])
            return getattr(imported, name)
        except (ImportError, AttributeError):
            continue
    logger.warning(f"could not import {module}.{name}, skipping the patch that needs it")
    return None
