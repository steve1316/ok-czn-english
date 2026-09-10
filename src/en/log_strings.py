"""The English that upstream's Chinese log lines come out as.

Data only - the matching lives in `src/en/log_text.py`. Split from it so a translation commit reads as a diff
of string pairs rather than of logic.

Both tables are keyed on the string as it was *written* in `ok_tasks/`, which is what
`scripts/scan_log_strings.py` prints. `MESSAGES` holds the lines with nothing interpolated. `TEMPLATES` holds
the rest, with each interpolation written `{}` on the left and `{0}`, `{1}` on the right, so the English can
put them in its own order. Storing shapes rather than regexes keeps the keys diffable against the extractor by
plain equality, and keeps anyone from having to hand-escape the parens sitting in a line like
`点击目标坐标=({}, {})`.

A shape with no entry is left in Chinese. That is the intended failure: `scan_log_strings.py --missing` names
it and `tests/TestLogText.py` fails on the coverage floor, where a half-translated line would just read as a
bug in the tool.
"""

# Lines written with nothing interpolated, keyed on the exact string.
MESSAGES = {}

# Lines written as f-strings, keyed on the literal runs with each interpolation collapsed to `{}`.
TEMPLATES = {}

# What a template's interpolations may themselves say. Several of them are handed a Chinese constant rather
# than a number - the `page=` label upstream gives a card read, the action word on a card screen - so without
# these a translated line still comes out with Chinese in the middle of it. Exact matches only: anything not
# listed is runtime data, usually a card name off the screen, and passes through untouched.
VALUES = {}
