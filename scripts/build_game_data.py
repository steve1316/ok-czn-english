"""Generate `src/en/game_data.py` and `src/en/game_text.py` from the game's own English localization table.

The Global client ships its text as `text/en/text.json`, a flat list of `{"id", "text"}` rows. That is the
authoritative source for card, equipment and combatant names, so the settings can offer real pick-lists
instead of asking the user to type a name and hope it matches. The same table carries each card's effect text,
which becomes the tooltip shown while picking.

Point `--dump` at the extracted `output` directory of a CZN asset rip. The dump itself is not committed - the
generated modules are, so the repo stays self-contained and a game patch is a re-run rather than a mystery.

Run `python scripts/build_game_data.py --dump <path-to-output>`.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "src" / "en" / "game_data.py"
OUT_TEXT_PATH = REPO_ROOT / "src" / "en" / "game_text.py"
DEFAULT_DUMP = Path(r"C:\Users\steve1316\Downloads\CZNRipper\output")

# Namespaces in the localization table, and the constant each becomes.
GROUPS = [
    ("CARDS", "Every card name, which covers Personas and Epiphanies too.",
     lambda table, dump: collect(table, r"card@name@")),
    ("EQUIPMENT", "Equipment, called relics internally.",
     lambda table, dump: collect(table, r"relic@name@")),
    ("NODE_TYPES", "Map node types, used for Route Priority.",
     lambda table, dump: collect(table, r"spot_type")),
    ("COMBATANTS", "Playable combatants, from the released roster rather than the dump.",
     lambda table, dump: collect_combatants(table, dump)),
]
# Combatants cannot be read out of the dump alone, from either direction. The `char_base@name@` namespace
# also names every NPC and enemy, and even the combatant table carries characters that have not been released
# yet, while a character released after the rip is missing from it altogether. So the roster below is the
# source of truth for who exists, and the dump is used to check it rather than to build it.
#
# Source: https://game8.co/games/Chaos-Zero-Nightmare/archives/558105 (checked 2026-09-03)
PLAYABLE_COMBATANTS = [
    "Adelheid", "Amir", "Arabella", "Beryl", "Cassius", "Chizuru", "Diana", "Fei", "Haru", "Heidemarie",
    "Hilde", "Hugo", "Kayron", "Khalipe", "Lucas", "Luke", "Magna", "Maribell", "Mei Lin", "Mika", "Narja",
    "Nia", "Nine", "Olga", "Orlea", "Owen", "Rei", "Renoa", "Rin", "Rita", "Selena", "Sereniel", "Tenebria",
    "Tiphera", "Tressa", "Veronica", "Yuki",
]
COMBATANT_TABLE = "char_base@char_combatant.json"
COMBATANT_NAME_ID = "char_base@name@{id}"
# Internal ids used for the developers' test units.
TEST_ID_PREFIX = "99"
# Placeholder rows the extraction should not carry into a dropdown.
JUNK = re.compile(r"^(test|temp|dummy|sample|todo|battle test|#)", re.I)

# Description namespaces, each paired with the name namespace it shares ids with.
DESCRIPTION_SOURCES = [
    ("card@desc@", "card@name@"),
    ("relic@s1_description@", "relic@name@"),
]
# The game's own markup, unwound in this order. A cross-reference resolves to the referenced card's name, so
# "Create X ^card@c_30097_cre1^" ends up reading "Create X Homing Laser L".
CARD_REFERENCE = re.compile(r"\^card@([^^]+)\^")
OTHER_REFERENCE = re.compile(r"\^[^^]+\^")
TERM_MARKER = re.compile(r"\$([^$#]+)(?:#\d+)?\$")
RUNTIME_VALUE = re.compile(r"#[a-zA-Z0-9_]+#")
COLOUR_TAG = re.compile(r"\[/?[a-z_]{0,15}\]")
STYLE_TAG = re.compile(r"</?[a-z]{0,3}>")
RUN_OF_SPACES = re.compile(r"[ \t]+")
# What a runtime value is shown as. The real number comes from per-card stat tables this table does not carry,
# and a tooltip only needs to say what a card does, not how far it scales.
VALUE_PLACEHOLDER = "X"


def load_table(dump_dir):
    """Read the English localization table from an asset dump.

    Args:
        dump_dir: Path to the dump's `output` directory.

    Returns:
        A dict of localization id to text.

    Raises:
        SystemExit: When the table is missing.
    """
    path = Path(dump_dir) / "text" / "en" / "text.json"
    if not path.exists():
        raise SystemExit(f"no localization table at {path}")
    table = {}
    for row in json.loads(path.read_text(encoding="utf-8")):
        table.setdefault(row["id"], row["text"])
    return table


def collect(table, pattern):
    """Pull the distinct, usable values for one namespace.

    Args:
        table: The localization table.
        pattern: Regex matched against the start of each id.

    Returns:
        A sorted list of distinct names.
    """
    names = set()
    for key, value in table.items():
        if re.match(pattern, key):
            text = (value or "").strip()
            if text and not JUNK.match(text):
                names.add(text)
    return sorted(names)


def collect_combatants(table, dump_dir):
    """Return the playable roster, and report where the dump disagrees with it.

    The roster decides who is in the list. The dump is only consulted to catch drift: a name the dump has
    never heard of is probably a typo, and a unit the dump carries that the roster does not is either
    unreleased or newly added and worth a look.

    Args:
        table: The localization table.
        dump_dir: Path to the dump's `output` directory.

    Returns:
        A sorted list of combatant names.

    Raises:
        SystemExit: When the combatant table is missing.
    """
    path = Path(dump_dir) / "db" / COMBATANT_TABLE
    if not path.exists():
        raise SystemExit(f"no combatant table at {path}")

    in_dump = set()
    for row in json.loads(path.read_text(encoding="utf-8")):
        combatant_id = str(row.get("id", ""))
        if combatant_id.startswith(TEST_ID_PREFIX):
            continue
        name = (table.get(COMBATANT_NAME_ID.format(id=combatant_id)) or "").strip()
        if name and not JUNK.match(name):
            in_dump.add(name)

    roster = set(PLAYABLE_COMBATANTS)
    for name in sorted(roster - in_dump):
        print(f"  note: '{name}' is on the roster but not in this dump, so the dump predates them")
    for name in sorted(in_dump - roster):
        print(f"  note: '{name}' is in the dump but not on the roster, so unreleased or newly added")
    return sorted(roster)


def clean_description(text, table):
    """Turn one raw description into the plain sentence a tooltip can show.

    Args:
        text: The raw description, carrying the game's own markup.
        table: The localization table, used to resolve card cross-references.

    Returns:
        The cleaned text, with a newline wherever the original had a line break.
    """
    text = CARD_REFERENCE.sub(lambda match: table.get("card@name@" + match.group(1), "that card"), text)
    text = OTHER_REFERENCE.sub("", text)
    text = text.replace("<br>", "\n")
    text = TERM_MARKER.sub(r"\1", text)
    text = RUNTIME_VALUE.sub(VALUE_PLACEHOLDER, text)
    text = COLOUR_TAG.sub("", text)
    text = STYLE_TAG.sub("", text)
    text = RUN_OF_SPACES.sub(" ", text)
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())


def collect_descriptions(table):
    """Pair every named card and relic with its effect text.

    Args:
        table: The localization table.

    Returns:
        A dict of entity name to cleaned description.
    """
    described = {}
    for desc_prefix, name_prefix in DESCRIPTION_SOURCES:
        names = {key[len(name_prefix):]: value for key, value in table.items() if key.startswith(name_prefix)}
        bodies = {key[len(desc_prefix):]: value for key, value in table.items() if key.startswith(desc_prefix)}
        chosen = {}
        for suffix, name in names.items():
            # A card appears once per upgrade tier under the same name. The shortest id is the base card.
            if suffix in bodies and (name not in chosen or len(suffix) < len(chosen[name])):
                chosen[name] = suffix
        for name, suffix in chosen.items():
            body = clean_description(bodies[suffix], table)
            # A description that only repeats the name tells the user nothing the tooltip does not already show.
            if not body or body == name:
                continue
            if name in described and described[name] != body:
                print(f"  note: '{name}' is named by two namespaces, keeping the first description")
                continue
            described[name] = body

    # A combatant can share a name with a card, and the combatant pickers look tooltips up the same way, so a
    # description here would explain something else entirely. One card loses its tooltip, which is the cheaper
    # half of the trade.
    for name in sorted(set(described) & set(PLAYABLE_COMBATANTS)):
        print(f"  note: '{name}' is both a combatant and a card, so its description is dropped")
        del described[name]
    return described


def render(groups, dump_dir):
    """Build the source of the generated module.

    Args:
        groups: A list of `(name, values, comment)` tuples.
        dump_dir: The dump the values came from, recorded in the header.

    Returns:
        The module source as a string.
    """
    lines = [
        '"""Game entity names taken from the Global client\'s own localization table.',
        "",
        "Generated by `scripts/build_game_data.py` - do not edit by hand. Re-run it after a game patch.",
        "",
        # Forward slashes so a Windows path cannot read as an escape sequence in the generated docstring.
        f"Source: {str(dump_dir).replace(chr(92), '/')}",
        f"Generated: {date.today().isoformat()}",
        '"""',
        "",
    ]
    for name, values, comment in groups:
        lines.append(f"# {comment}")
        lines.append(f"{name} = [")
        lines.extend(f"    {value!r}," for value in values)
        lines.append("]")
        lines.append("")
    return "\n".join(lines)


def render_descriptions(described, dump_dir):
    """Build the source of the generated description module.

    Args:
        described: A dict of entity name to cleaned description.
        dump_dir: The dump the text came from, recorded in the header.

    Returns:
        The module source as a string.
    """
    lines = [
        '"""Card and equipment effect text, taken from the Global client\'s own localization table.',
        "",
        "Generated by `scripts/build_game_data.py` - do not edit by hand. Re-run it after a game patch.",
        "",
        f"Source: {str(dump_dir).replace(chr(92), '/')}",
        f"Generated: {date.today().isoformat()}",
        '"""',
        "",
        "# Keyed by the same names as the rosters in `game_data.py`. `X` stands in for a value the game fills in",
        "# at runtime from stat tables the localization table does not carry.",
        "DESCRIPTIONS = {",
    ]
    lines.extend(f"    {name!r}: {described[name]!r}," for name in sorted(described))
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main():
    """Entry point. Writes the generated modules and reports what they hold.

    Returns:
        0 on success.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump", default=str(DEFAULT_DUMP), help="path to the asset dump's output directory")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    table = load_table(args.dump)
    groups = [(name, collector(table, args.dump), comment) for name, comment, collector in GROUPS]
    described = collect_descriptions(table)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(groups, args.dump), encoding="utf-8")
    OUT_TEXT_PATH.write_text(render_descriptions(described, args.dump), encoding="utf-8")

    print(f"read {len(table)} localization rows from {args.dump}")
    for name, values, _ in groups:
        with_text = sum(1 for value in values if value in described)
        print(f"  {name:12} {len(values):5d}   {with_text:5d} described")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {OUT_TEXT_PATH.relative_to(REPO_ROOT)} with {len(described)} descriptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
