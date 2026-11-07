"""Resolve the ok-script UI classes the patches reach for.

Every patch module under `src/en/` reaches into ok-script internals, and a class can move or disappear between
releases. Looking them up through here keeps a missing class a skipped patch rather than a crash on startup.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# Where ok-script keeps its live UI. `ok.gui` is only a compatibility alias of it now.
UI_PACKAGE = "ok.ui.qt"


def import_ui(module, name):
    """Import one framework UI attribute.

    Args:
        module: Module path below the UI package, such as `tasks.config_form`.
        name: Class or constant to pull out of it.

    Returns:
        The attribute, or None when ok-script no longer provides it.
    """
    try:
        return getattr(__import__(f"{UI_PACKAGE}.{module}", fromlist=[name]), name)
    except (ImportError, AttributeError):
        logger.warning(f"could not import {module}.{name}, skipping the patch that needs it")
        return None
