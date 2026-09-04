"""Report how much of the game text the handlers look for is covered by the reverse OCR catalog.

The handlers in `ok_tasks/` identify pages by comparing OCR text against Chinese literals. On the Global
client those comparisons only succeed if `i18n/en_US/LC_MESSAGES/ocr.po` rewrites the English into a string
that satisfies them. This walks the sources for every such literal and checks the catalog against it, which is
the progress measure for the English port.

A literal counts as covered when some msgstr contains it, or matches it when the literal is a regex.

Run `python scripts/check_vocab.py`, or add `--remaining` to list only what is still missing.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "ok_tasks"
OCR_PO = REPO_ROOT / "i18n" / "en_US" / "LC_MESSAGES" / "ocr.po"
CJK = re.compile(r"[\u4e00-\u9fff]")
REGEX_CHARS = re.compile(r"[.*+?()\[\]\|]")

# How the handlers test OCR text. Each pattern captures the literal being compared against.
COMPARISONS = [
    ("clean_match", re.compile(r'_clean_match\([^,]+,\s*["\']([^"\']+)["\']')),
    ("name ==", re.compile(r'\.name\s*==\s*["\']([^"\']+)["\']')),
    ("in name", re.compile(r'["\']([^"\']+)["\']\s+in\s+\w+\.name')),
    ("find_text", re.compile(r'find_text\(task,\s*r?["\']([^"\']+)["\']')),
    ("re.search", re.compile(r're\.search\(\s*r?["\']([^"\']+)["\']')),
    ("get_game_text", re.compile(r'_get_game_text\(task,\s*["\']([^"\']+)["\']')),
]


def collect_literals():
    """Find every Chinese literal the task sources compare OCR text against.

    Returns:
        A dict of literal to the sorted set of comparison kinds that use it.
    """
    literals = defaultdict(set)
    for path in sorted(TASKS_DIR.glob("*.py")):
        # Commented-out handlers still parse as comparisons, so drop comments before scanning.
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")]
        text = chr(10).join(lines)
        for kind, pattern in COMPARISONS:
            for match in pattern.finditer(text):
                if CJK.search(match.group(1)):
                    literals[match.group(1)].add(kind)
    return literals


def is_satisfied(literal, msgstrs):
    """Report whether any catalog translation would satisfy one comparison.

    Args:
        literal: The Chinese literal a handler compares against.
        msgstrs: Every msgstr in the reverse OCR catalog.

    Returns:
        True when some msgstr contains the literal, or matches it when it is a regex.
    """
    if REGEX_CHARS.search(literal):
        try:
            return any(re.search(literal, m) for m in msgstrs)
        except re.error:
            return False
    return any(literal in m for m in msgstrs)


def main():
    """Entry point. Prints catalog coverage of the literals the handlers rely on.

    Returns:
        0 always, so this reports rather than gates.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remaining", action="store_true", help="list only the uncovered literals")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    literals = collect_literals()
    msgstrs = [e.msgstr for e in polib.pofile(str(OCR_PO)) if e.msgid and e.msgstr]
    remaining = sorted((l for l in literals if not is_satisfied(l, msgstrs)), key=len, reverse=True)
    covered = len(literals) - len(remaining)

    print(f"covered {covered}/{len(literals)} literals\n")
    if not args.remaining:
        for literal in sorted(l for l in literals if is_satisfied(l, msgstrs)):
            print(f"  ok       {literal}")
        print()
    for literal in remaining:
        print(f"  missing  {literal}   [{','.join(sorted(literals[literal]))}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
