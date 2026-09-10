"""Change which page handlers a mode runs, without touching `ok_tasks/`.

Each mode keeps an ordered `PAGE_HANDLERS` list and its run loop takes the first handler returning True. Two
things make editing those lists fiddlier than it looks. They hold function objects, so rebinding a name on the
module changes nothing and the list itself has to be edited. And they do not exist yet when `Globals` is built:
ok-script constructs `my_app` before `TaskManager` puts `ok_tasks/` on `sys.path` and imports the modes - four
milliseconds apart in a real launch, but an ordering all the same - so an edit made from `apply()` would
silently find nothing. Registering it here defers it to `BaseTask.after_init`, which runs once per task after
that module has been imported.

The modes are found by shape rather than by name. They are imported flat (`utils_chaos`, not
`ok_tasks.utils_chaos`), a future mode would be missed by a hardcoded list, and `utils_story` has a
`PAGE_HANDLERS` of its own containing neither handler we touch. All three fall out of looking for the attribute.

`StandIn` covers a second shape. Upstream reaches for `random.choice` in several places in one module and a
fork change usually wants exactly one of them, so both `src/en/events.py` and `src/en/battle.py` stand in for
the whole module for the length of one call. `standing_in` is the third and most common: rather than
reimplement a two-hundred-line handler, run it exactly as it is over a different answer to one question. Its
save-set-restore has to be exception-safe every time, because a handler that throws while a module attribute is
swapped would leave upstream permanently rewired.
"""

import contextlib
import sys

from ok import Logger

logger = Logger.get_logger(__name__)

HANDLER_LIST = "PAGE_HANDLERS"
# Stands for "the target had none of its own", which for an object means the name came from its class.
OWNED_BY_CLASS = object()
# Records which fork-local changes a function already carries, so each is applied exactly once
# however many modules wrap the same upstream function and however often the installs re-run.
WRAPS = "_en_wraps"

_pending = []
_hooked = False


class StandIn:
    """Stands in for a module upstream calls, answering one question and passing the rest along.

    A subclass overrides the one call it wants to take over and leaves everything else to the passthrough,
    so an unrelated use of the same module carries on behaving exactly as it did.
    """

    def __init__(self, original):
        """Hold the module being stood in for.

        Args:
            original: The module upstream would otherwise have used.
        """
        self.original = original

    def __getattr__(self, name):
        """Hand anything the subclass does not answer straight to the real module.

        Args:
            name: The attribute being looked up.

        Returns:
            The real module's attribute.
        """
        return getattr(self.original, name)


@contextlib.contextmanager
def standing_in(target, **replacements):
    """Swap attributes on a module or object for the length of a block.

    What is put back depends on where the name came from, which is why the original is read out of the
    target's own `__dict__` rather than with `getattr`. A module attribute, or an instance attribute like
    `all_texts`, is the target's own and is simply restored. A method is not: it lives on the class, and
    setting it back by name would leave a bound copy on the instance shadowing the class for the rest of the
    app's life, holding a reference cycle with the task. Removing what was set puts that lookup back.

    Args:
        target: The module or object whose attributes are being stood in for.
        **replacements: The attribute names to swap, and what to put in their place.

    Returns:
        A context manager that restores every original on the way out, however the block ends.
    """
    held = vars(target)
    originals = {name: held.get(name, OWNED_BY_CLASS) for name in replacements}
    for name, replacement in replacements.items():
        setattr(target, name, replacement)
    try:
        yield
    finally:
        for name, original in originals.items():
            if original is OWNED_BY_CLASS:
                vars(target).pop(name, None)
            else:
                setattr(target, name, original)


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


def wrap(module, name, factory, tag):
    """Compose a fork-local change over an upstream function, everywhere the run reaches it.

    Two modules wrapping the same function is normal here, and so is the install running once per task load, so
    one shared record of what a function already carries is what keeps the stack from growing per module per load.

    The wrapper goes in two places because the two are reached differently. A page handler is only ever called
    through a mode's list, which holds function objects, so the list entry has to be replaced. A helper like
    `select_card` is called as a module global and is in no list. Doing both covers either kind, and covers a
    handler that other patches rebuild by reading the module attribute back.

    Args:
        module: The module holding the function, normally `utils`.
        name: The function's name on that module.
        factory: Takes the function currently installed and returns the wrapper to put in its place.
        tag: Names this particular change, so it is applied once and no more.
    """
    current = getattr(module, name, None)
    if current is None:
        return
    if tag not in getattr(current, WRAPS, ()):
        wrapped = factory(current)
        # Position is the priority scheme and `replace` matches by name, so the name has to survive.
        wrapped.__name__ = getattr(current, "__name__", name)
        setattr(wrapped, WRAPS, (*getattr(current, WRAPS, ()), tag))
        setattr(module, name, wrapped)
        current = wrapped
        logger.info(f"{name} now carries {tag}")
    # Re-checked on every load rather than only on the first: the modes are imported one at a time, so a list
    # that did not exist when this ran before still needs the wrapper now.
    replace(name, current)


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


def append(handler, anchor_name):
    """Register a handler to run after every existing one, in the modes carrying a given handler.

    Last is its own kind of precedence: a handler here only sees a frame every handler recognising a screen by
    name has already declined, which is what makes acting on shape alone safe.

    The anchor is what keeps that from spreading. `replace` and `insert_before` scope themselves to lists holding
    the handler they name, and appending has no such brake, so it would reach every mode loaded now and every mode
    added later. The anchor only decides *which* lists change, never where in them the handler lands.

    Args:
        handler: The function to append.
        anchor_name: `__name__` of a handler the intended modes carry and others do not.

    Returns:
        The number of lists changed.
    """
    changed = 0
    for module_name, handlers in each_list():
        names = [getattr(existing, "__name__", None) for existing in handlers]
        # Matched by name for the same reason `insert_before` does it: the install runs once per task load.
        if anchor_name not in names or handler.__name__ in names:
            continue
        handlers.append(handler)
        changed += 1
        logger.info(f"{module_name}: {handler.__name__} appended at {len(handlers) - 1}")
    return changed


def register(install):
    """Arrange for a handler-list edit to run once the modes have been imported.

    Args:
        install: A callable taking no arguments that performs the edit. It is run on every task load, so it
            must be idempotent - `replace`, `insert_before` and `append` all are.
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
