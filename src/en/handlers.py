"""Change which page handlers a mode runs, without touching `ok_tasks/`.

Each mode keeps an ordered list of page handlers - `PAGE_HANDLERS` in `ok_tasks/utils_chaos.py` and
`ok_tasks/utils_sortie.py` - and its run loop takes the first one that returns True. Two things make editing
those lists fiddlier than it looks, and both are handled here.

**They are lists of function objects.** Rebinding a name on the module changes nothing, because the list still
holds the original function. Any fork-local change has to edit the list itself.

**They do not exist yet when `Globals` is built.** ok-script constructs `my_app` before `TaskManager` puts
`ok_tasks/` on `sys.path` and imports the modes - four milliseconds apart in a real launch, but an ordering
all the same. So an edit made from `apply()` would silently find nothing. Registering the edit here defers it
until `BaseTask.after_init`, which runs once per task after its module has been imported.

The modes are found by shape rather than by name. They are imported flat (`utils_chaos`, not
`ok_tasks.utils_chaos`), a future mode would be missed by a hardcoded list, and `utils_story` has a
`PAGE_HANDLERS` of its own that happens to contain neither handler we touch - all three cases fall out of
looking for the attribute instead of the module name.
"""

import sys

from ok import Logger

logger = Logger.get_logger(__name__)

HANDLER_LIST = "PAGE_HANDLERS"

_pending = []
_hooked = False


def each_list():
    """Yield every handler list the task modules have loaded.

    Returns:
        A generator of `(module_name, list)` pairs.
    """
    for name, module in list(sys.modules.items()):
        handlers = getattr(module, HANDLER_LIST, None)
        if isinstance(handlers, list) and handlers:
            yield name, handlers


def loaded(module_name):
    """Look up a task module without importing it.

    The installs run on every task load, and the modes are imported one at a time, so a module simply not
    being there yet is the normal case rather than a failure. Importing it here would either raise, or drag
    it in ahead of the framework's own loader.

    Args:
        module_name: The flat module name, such as `utils_chaos`.

    Returns:
        The module, or None when it has not been imported yet.
    """
    return sys.modules.get(module_name)


def replace(original_name, replacement):
    """Swap a handler for another wherever it is registered, keeping its position.

    Position is the priority scheme in this codebase, so the replacement takes the original's index rather
    than being appended.

    Args:
        original_name: `__name__` of the upstream handler to stand down.
        replacement: The function to run in its place.

    Returns:
        The number of lists changed.
    """
    changed = 0
    for module_name, handlers in each_list():
        for index, handler in enumerate(handlers):
            if handler is replacement:
                break
            if getattr(handler, "__name__", None) == original_name:
                handlers[index] = replacement
                changed += 1
                logger.info(f"{module_name}: {original_name} replaced at index {index}")
                break
    return changed


def insert_before(anchor_name, handler):
    """Register a handler to run just ahead of an existing one.

    Immediately before the anchor, not at the front: everything above keeps its precedence, and the anchor
    becomes the fallback for whatever the new handler declines.

    Args:
        anchor_name: `__name__` of the upstream handler to sit in front of.
        handler: The function to insert.

    Returns:
        The number of lists changed.
    """
    changed = 0
    for module_name, handlers in each_list():
        # Matched by name, not identity: `install` builds a fresh function each time it runs, and it runs
        # once per task load, so an identity test would insert a duplicate every time.
        if any(getattr(existing, "__name__", None) == handler.__name__ for existing in handlers):
            continue
        for index, existing in enumerate(handlers):
            if getattr(existing, "__name__", None) == anchor_name:
                handlers.insert(index, handler)
                changed += 1
                logger.info(f"{module_name}: {handler.__name__} inserted before {anchor_name} at {index}")
                break
    return changed


def register(install):
    """Arrange for a handler-list edit to run once the modes have been imported.

    Args:
        install: A callable taking no arguments that performs the edit. It is run on every task load, so it
            must be idempotent - `replace` and `insert_before` both are.
    """
    global _hooked
    _pending.append(install)
    if _hooked:
        return
    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, handler list edits will not be applied")
        return

    original_after_init = BaseTask.after_init

    def patched_after_init(self, *args, **kwargs):
        result = original_after_init(self, *args, **kwargs)
        for pending in _pending:
            try:
                pending()
            except Exception as error:
                # A failed edit must never stop a task from loading; the mode simply keeps upstream behaviour.
                logger.error(f"could not apply {pending}: {error}", exception=error)
        return result

    BaseTask.after_init = patched_after_init
    _hooked = True
