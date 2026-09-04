"""List every Chinese string the app shows in its own GUI, so `ok.po` can be kept complete.

These are task names, setting keys, help text, dropdown values and button labels - not game text. Game text
read off the screen belongs in `ocr.po`, which runs the other way.

Upstream ships a scanner at `.agents/skills/ok-script-i18n/`, but it only understands whole-dict assignment
(`self.default_config = {...}`). This repo sets most keys by subscript (`self.default_config['x'] = ...`), so
those never showed up. This walks the same attributes and handles both forms.

Run `python scripts/scan_ui_strings.py`, or add `--missing` to list only what `ok.po` does not translate yet.
"""

import argparse
import ast
import re
import sys
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = [REPO_ROOT / "ok_tasks", REPO_ROOT / "src"]
OK_PO = REPO_ROOT / "i18n" / "en_US" / "LC_MESSAGES" / "ok.po"
CJK = re.compile(r"[\u4e00-\u9fff]")

# Attributes whose keys and values are shown in the settings UI.
UI_DICTS = {"default_config", "config_description", "config_type"}
UI_STRINGS = {"name", "description"}
# config_type metadata, not user-visible text.
META = {"type", "options", "options_available", "buttons", "sub_configs", "text", "callback", "selector_type",
        "drop_down", "multi_selection", "global", "text_edit", "button", "range", "filter", "dialog_title"}


def literal_strings(node):
    """Collect every Chinese string constant inside one AST node.

    Args:
        node: The AST node to walk.

    Returns:
        A list of Chinese strings found, in source order.
    """
    found = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and CJK.search(child.value):
            found.append(child.value)
    return found


def scan_file(path):
    """Find the GUI strings one source file contributes.

    Args:
        path: Path to a Python source file.

    Returns:
        A pair of sets: the labels shown in the interface, and the game-data default values under them.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    found = set()
    values = set()
    for node in ast.walk(tree):
        # self.name = "..." and self.description = "..."
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in UI_STRINGS:
                    found.update(literal_strings(node.value))
                # self.default_config['key'] = value, and the same for the other UI dicts.
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Attribute):
                    if target.value.attr in UI_DICTS:
                        found.update(literal_strings(target.slice))
                        # A default_config value is game data the user edits (card and combatant names), not a
                        # label. It is matched against OCR text that ocr.po has already turned back into
                        # Chinese, so translating it would stop those comparisons working.
                        if target.value.attr == "default_config":
                            values.update(literal_strings(node.value))
                        else:
                            found.update(literal_strings(node.value))
                # self.default_config = {...}
                if isinstance(target, ast.Attribute) and target.attr in UI_DICTS:
                    found.update(literal_strings(node.value))
        # ConfigOption('名称', {...}, description='...') in src/config.py
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ConfigOption":
            found.update(literal_strings(node))

    return {s for s in found if s not in META}, {s for s in values if s not in META}


def main():
    """Entry point. Prints the GUI strings, or only the untranslated ones.

    Returns:
        0 always.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--missing", action="store_true", help="only show strings ok.po does not translate")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    strings, values = set(), set()
    for root in SOURCES:
        for path in sorted(root.rglob("*.py")):
            labels, defaults = scan_file(path)
            strings |= labels
            values |= defaults
    strings -= values

    translated = {e.msgid for e in polib.pofile(str(OK_PO)) if e.msgid and e.msgstr}
    missing = sorted(strings - translated, key=len)

    print(f"{len(strings)} GUI labels, {len(strings) - len(missing)} translated, {len(missing)} missing")
    print(f"{len(values)} default values left in Chinese on purpose, since they are matched against OCR text")
    print()
    for text in (missing if args.missing else sorted(strings, key=len)):
        mark = "  " if text in translated else "->"
        print(f"{mark} {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
