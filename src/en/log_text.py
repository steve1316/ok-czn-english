"""Say upstream's log lines in English, without editing `ok_tasks/`.

Every Chinese line the app writes comes from `ok_tasks/` - 472 call sites across seven files. The installed
framework has one, a MuMu warning, and `src/en/` already logs in English. So this is the whole of it, and
since `ok_tasks/` is vendored the rewrite has to happen on the way out.

`BaseTask.log_info` fans out to three places - `self.logger.info`, the Tasks tab's `Log` row via `info_set`,
and the Windows toast when `notify=True` - so translating at the top of it covers all three. A filter on the
logging module would have covered only the first.

Nothing reads log text, so this is safe: `handle_stuck_log` sounds like an exception but decides by pixel diff
in `is_frame_stuck`. The Chinese that *is* load-bearing - OCR comparison literals, `feature_types` labels,
config keys, the handler names `src/en/` targets - is never a log-message argument, so patching at the
argument position cannot reach it.

The pair to this is `src/en/ocr_text.py`, which runs the other way: that one rewrites English read off the
screen back into the Chinese the handlers compare against.
"""

import re

from ok import Logger

from src.en.log_strings import MESSAGES, TEMPLATES, VALUES

logger = Logger.get_logger(__name__)

# One C-level scan that exits on the first character for anything already English. This runs on every log call
# in the polling loop, so it is what keeps the cost of the patch off the framework's own lines and off ours.
CJK = re.compile(r"[一-鿿]")
# The methods on `BaseTask` that take a message as their first positional argument.
LOG_METHODS = ("log_info", "log_debug", "log_warning", "log_error")

# `TEMPLATES`, compiled and grouped by the first character of the shape, so a Chinese line tries a handful of
# patterns rather than all of them. Shapes opening with an interpolation have no such character and are tried
# afterwards. Both are filled by `_compile_templates` at import.
BY_FIRST_CHARACTER = {}
ANCHORLESS = ()

_patched = False


def compile_template(shape):
    """Turn a written shape into a pattern that matches the line it renders as.

    The literal runs are escaped and the interpolations become `(.*?)`. Non-greedy is safe because no site in
    `ok_tasks/` writes two interpolations with nothing between them, so every group has a literal on both
    sides to stop at, and the whole pattern is anchored. Empty is allowed because an interpolation really can
    render as nothing: `node_type` starts as `""`, so the run's first status row reads `第1层，第0节点，`.

    Args:
        shape: The Chinese line as written, with each interpolation collapsed to `{}`.

    Returns:
        A compiled pattern anchored to the whole line.
    """
    return re.compile("^" + "(.*?)".join(re.escape(part) for part in shape.split("{}")) + r"\Z", re.DOTALL)


def _compile_templates():
    """Fill the lookups `translate` walks, ordering each so a more specific shape is tried first."""
    global ANCHORLESS
    buckets = {}
    anchorless = []
    for shape, english in TEMPLATES.items():
        entry = (len(shape), compile_template(shape), english)
        target = anchorless if shape.startswith("{}") else buckets.setdefault(shape[0], [])
        target.append(entry)

    # Longest shape first, so one that is another's prefix cannot swallow it.
    def ordered(entries):
        return tuple((pattern, english) for _, pattern, english in sorted(entries, key=lambda entry: -entry[0]))

    BY_FIRST_CHARACTER.clear()
    BY_FIRST_CHARACTER.update({first: ordered(entries) for first, entries in buckets.items()})
    ANCHORLESS = ordered(anchorless)


def translate(text):
    """Give the English for one written line, or hand it back unchanged.

    Args:
        text: The message a handler passed to one of the logging methods, or an `info_set` key or value.

    Returns:
        The English, or `text` itself when it carries no Chinese or no entry covers it.
    """
    if not isinstance(text, str) or not text or not CJK.search(text):
        return text
    exact = MESSAGES.get(text)
    if exact is not None:
        return exact
    for pattern, english in BY_FIRST_CHARACTER.get(text[0], ()) + ANCHORLESS:
        if found := pattern.match(text):
            # An interpolation can be a Chinese constant itself, so each captured piece gets the same lookup.
            return english.format(*(VALUES.get(piece, piece) for piece in found.groups()))
    return text


def translating(original):
    """Wrap one logging method so its message arrives in English.

    Args:
        original: The unbound method being replaced.

    Returns:
        The replacement, forwarding everything but the message untouched.
    """
    def logging_in_english(self, message, *args, **kwargs):
        # `log_error` carries an extra positional and the rest have keyword-only extras, so nothing beyond the
        # message is respelled here. ok-script has grown arguments on these before.
        return original(self, translate(message), *args, **kwargs)

    return logging_in_english


def reporting(original):
    """Wrap `info_set` so the Tasks tab draws its Info rows in English.

    A row's key and value both reach `og.app.tr` in `TaskTab.update_task_info`, so most of these could have
    been catalog entries instead. Three could not: the floor and node row, the equipment row and the
    meditation key are composed at runtime, and `tr` is a whole-string lookup. Doing all of them here keeps
    one mechanism rather than two, and an English string that is not a msgid comes back from `tr` unchanged.

    Args:
        original: The unbound `info_set` being replaced.

    Returns:
        The replacement.
    """
    def info_set_in_english(self, key, value):
        return original(self, translate(key), translate(value))

    return info_set_in_english


def apply():
    """Route every message `ok_tasks/` logs, and every row it reports, through the translation table."""
    global _patched
    if _patched:
        return

    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, upstream's log lines will stay in Chinese")
        _patched = True
        return

    _compile_templates()
    for name in LOG_METHODS:
        original = getattr(BaseTask, name, None)
        if original is None:
            logger.warning(f"BaseTask has no {name}, leaving those lines in Chinese")
            continue
        setattr(BaseTask, name, translating(original))
    if hasattr(BaseTask, "info_set"):
        # After the logging methods, so `log_info`'s own `info_set("Log", ...)` call hands over a message that
        # is already English. The second pass costs one failed character test, which is why the order is free.
        BaseTask.info_set = reporting(BaseTask.info_set)
    logger.info(f"{len(MESSAGES)} log messages and {len(TEMPLATES)} templates installed")
    _patched = True
