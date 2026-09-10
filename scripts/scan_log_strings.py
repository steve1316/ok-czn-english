"""List every Chinese string `ok_tasks/` writes to the log, so `src/en/log_strings.py` can be kept complete.

`ok_tasks/` is vendored, so its log calls stay in Chinese and are translated at runtime instead. Matching them
needs the string as it was *written*, not as it was rendered, so each call's first argument is collapsed to a
shape: a plain string keeps its text, and an f-string keeps its literal runs with each interpolation replaced
by `{}`. `log_strings.py` is keyed on exactly those shapes, so checking coverage is string equality and a
rebase that rewords one line shows up here as a missing shape rather than as silence.

Run `python scripts/scan_log_strings.py`, `--missing` for only what is untranslated, or `--stubs` for
paste-ready table entries.
"""

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "ok_tasks"
CJK = re.compile(r"[一-鿿]")
# The logging methods `BaseTask` offers. Every one of them takes the message as its first positional argument.
LOG_METHODS = {"log_info", "log_debug", "log_warning", "log_error"}
# A replacement field in a `.format()` template, collapsed the same way an f-string's is.
FIELD = re.compile(r"\{[^{}]*\}")


def shape_of(node):
    """Collapse one log-call argument to the shape `log_strings.py` is keyed on.

    Args:
        node: The AST node for the call's first positional argument.

    Returns:
        The shape, with each interpolation written as `{}`, or None when the argument carries no Chinese or is
        not a form worth matching - a bare variable, say, whose text is not in this file at all.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        shape = node.value
    elif isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            elif isinstance(piece, ast.FormattedValue):
                parts.append("{}")
            else:
                return None
        shape = "".join(parts)
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"
            and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str)):
        shape = FIELD.sub("{}", node.func.value.value)
    else:
        return None
    return shape if CJK.search(shape) else None


def scan_file(path):
    """Find the log shapes one source file contributes.

    Args:
        path: Path to a Python source file.

    Returns:
        A list of `(lineno, shape)` pairs, in source order.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LOG_METHODS or not node.args:
            continue
        shape = shape_of(node.args[0])
        if shape is not None:
            found.append((node.lineno, shape))
    return found


def collect_shapes():
    """Walk `ok_tasks/` and gather every Chinese log shape with the call sites that write it.

    Imported by `tests/TestLogText.py`, which fails when coverage of these shapes drops.

    Returns:
        A dict of shape to a sorted list of `"file.py:line"` call sites.
    """
    sites = defaultdict(list)
    for path in sorted(TASKS_DIR.rglob("*.py")):
        for lineno, shape in scan_file(path):
            sites[shape].append(f"{path.name}:{lineno}")
    return {shape: sorted(where) for shape, where in sites.items()}


def translated_shapes():
    """Read the shapes `src/en/log_strings.py` already carries.

    Returns:
        A pair of sets: the exact messages, and the templated shapes. Both empty when the table does not exist
        yet, which is the state this scanner is first run in.
    """
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from src.en import log_strings
    except ImportError:
        return set(), set()
    return set(log_strings.MESSAGES), set(log_strings.TEMPLATES)


def main():
    """Entry point. Prints coverage of the Chinese log strings, or only what is missing.

    Returns:
        0 always.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--missing", action="store_true", help="only show shapes log_strings.py does not carry")
    parser.add_argument("--stubs", action="store_true", help="print paste-ready table entries for those shapes")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sites = collect_shapes()
    messages, templates = translated_shapes()
    done = messages | templates
    exact = {shape for shape in sites if "{}" not in shape}
    shaped = set(sites) - exact
    missing = set(sites) - done

    covered = len(sites) - len(missing)
    percent = 100 * covered // len(sites) if sites else 100
    print(f"{len(sites)} log strings, {covered} translated, {len(missing)} missing  ({percent}%)")
    print(f"  exact      {len(exact)} strings, {len(exact - missing)} translated")
    print(f"  templated  {len(shaped)} shapes,  {len(shaped - missing)} translated")
    print()

    # Hottest first, so the translation commits land in the order a run actually meets them.
    listed = sorted(missing if (args.missing or args.stubs) else set(sites),
                    key=lambda shape: (-len(sites[shape]), sites[shape][0]))
    for shape in listed:
        where = ", ".join(sites[shape][:3]) + (" ..." if len(sites[shape]) > 3 else "")
        if args.stubs:
            print(f'    "{shape}": "",  # {where}')
        else:
            print(f"{'  ' if shape in done else '->'} {shape}")
            print(f"     {where}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
