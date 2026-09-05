"""Generate `src/en/game_data.py` and `src/en/game_text.py` from the game's own English localization table.

The Global client ships its text as `text/en/text.json`, a flat list of `{"id", "text"}` rows. That is the
authoritative source for card, equipment and combatant names, so the settings can offer real pick-lists
instead of asking the user to type a name and hope it matches.

The same dump carries each card's effect text, which becomes the tooltip shown while picking. That text is
written against placeholders rather than numbers - `#result_ev_0#` means "the value of my first linked effect"
- so the effect and equipment tables are loaded too and the numbers filled in.

Point `--dump` at the extracted `output` directory of a CZN asset rip. The dump itself is not committed - the
generated modules are, so the repo stays self-contained and a game patch is a re-run rather than a mystery.

Run `python scripts/build_game_data.py --dump <path-to-output>`, or set `CZN_DUMP` and run it bare.
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "src" / "en" / "game_data.py"
OUT_TEXT_PATH = REPO_ROOT / "src" / "en" / "game_text.py"
OUT_QUALITY_PATH = REPO_ROOT / "src" / "en" / "game_quality.py"
# Where the extracted asset dump lives. Set CZN_DUMP, or pass --dump. Deliberately not a real path:
# these modules are committed, and a default pointing at one machine would be copied into all of them.
DUMP_ENV = "CZN_DUMP"
DEFAULT_DUMP = Path(os.environ.get(DUMP_ENV, "dump"))
# Stamped into every generated module in place of the dump path, for the same reason.
SOURCE_NOTE = "Source: the Global client's own asset dump."

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

# The dump splits its tables per game mode, so each of these is a glob. The second entry is a column only that
# kind of table has, which keeps unrelated files with the same suffix out.
CARD_TABLES = ("*card.json", "link_skill_eff_id")
EFFECT_TABLES = ("*skill_eff.json", "eff_value")
RELIC_TABLES = ("*relic.json", "s1_cs_value")

# A card addresses its own linked effects by position, so `#result_ev_0#` is the first linked effect's value
# and `#result_ecv_1#` the second one's count. The prefix varies with where the text is shown and does not
# change which column is read, so only the `ev` / `ecv` / `damage` part of the name matters.
CARD_PLACEHOLDER = re.compile(r"#([a-z][a-z0-9_]*)_(\d+)#")
VALUE_COLUMN = "eff_value"
COUNT_COLUMN = "eff_count_value"
CARD_VALUE_KINDS = {"ecv": COUNT_COLUMN, "ev": VALUE_COLUMN, "damage": VALUE_COLUMN}
# Effects whose value is a coefficient the game shows as a percentage, so "300 Damage" is really "300%".
#
# The data pins this list rather than guesswork. Several placeholder families come in a plain and a `pct_off`
# spelling, and every one of the 177 `pct_off` uses is followed by a literal `%` in the text while their plain
# counterparts almost never are - so `pct_off` means "the sign is written out here" and the plain spelling
# means the game appends it. These are the effect types those pairs point at.
PERCENT_EFFECTS = {"SKILL_EFF_DMG", "SKILL_EFF_SHIELD", "SKILL_EFF_CURE", "SKILL_EFF_DAMAGE_VALUE_ADD"}
# A count is a number of hits or cards even on a damage effect, as in "50% Damage x 4", so it never takes a sign.
MARKUP_PREFIX = re.compile(r"^(\[/?[a-z_]*\]|</?[a-z]{0,3}>)+")
# The `cs_` families reach through a character-stat table this does not load, and their linked effect holds a
# stack count rather than the number shown, so resolving them from here would print a confidently wrong value.
UNRESOLVED_FAMILY = "cs_"
# Equipment keeps its numbers on the relic row itself: `#rev_1_0#` is the second entry of its value list.
RELIC_PLACEHOLDER = re.compile(r"#rev_(\d+)_\d+#")
RELIC_NB_PLACEHOLDER = re.compile(r"#nbev_(\d+)#")
LIST_ENTRY = re.compile(r"[^\[\],\s]+")

# The game's own markup, unwound in this order. A cross-reference resolves to the referenced card's name, so
# "Create X ^card@c_30097_cre1^" ends up reading "Create X Homing Laser L".
CARD_REFERENCE = re.compile(r"\^card@([^^]+)\^")
OTHER_REFERENCE = re.compile(r"\^[^^]+\^")
TERM_MARKER = re.compile(r"\$([^$#]+)(?:#\d+)?\$")
RUNTIME_VALUE = re.compile(r"#[a-zA-Z0-9_]+#")
COLOUR_TAG = re.compile(r"\[/?[a-z_]{0,15}\]")
STYLE_TAG = re.compile(r"</?[a-z]{0,3}>")
RUN_OF_SPACES = re.compile(r"[ \t]+")
# Shown in place of a value that could not be resolved, so the sentence still reads.
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


def load_data_tables(dump_dir, spec):
    """Load every data table matching one glob, keyed by row id.

    Args:
        dump_dir: Path to the dump's `output` directory.
        spec: A `(glob, required_column)` pair. The column keeps same-suffix tables of another shape out.

    Returns:
        A dict of row id to row.
    """
    pattern, required = spec
    rows = {}
    for path in sorted(Path(dump_dir, "db").glob(pattern)):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data and required in data[0]:
            for row in data:
                rows.setdefault(row["id"], row)
    return rows


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


def card_value_field(family):
    """Say which effect column a card placeholder reads, if any.

    Args:
        family: The placeholder name with its trailing index removed, such as `result_coeff_ev`.

    Returns:
        The column name, or None when this family cannot be resolved from the tables loaded here.
    """
    if family.startswith(UNRESOLVED_FAMILY):
        return None
    parts = set(family.split("_"))
    for kind, column in CARD_VALUE_KINDS.items():
        if kind in parts:
            return column
    return None


def needs_percent(effect, column, text, position):
    """Decide whether a resolved value should be written with a percent sign.

    Args:
        effect: The linked effect row the value came from.
        column: The column that was read.
        text: The whole raw description.
        position: Where the placeholder ended, so the following text can be checked.

    Returns:
        True when the game would show this value as a percentage and the text does not write the sign itself.
    """
    if column != VALUE_COLUMN or effect.get("eff") not in PERCENT_EFFECTS:
        return False
    return not MARKUP_PREFIX.sub("", text[position:]).startswith("%")


def resolve_card_values(text, card, effects):
    """Fill a card's placeholders in from its linked effects.

    Args:
        text: The raw description.
        card: The card's row, whose `link_skill_eff_id` orders the effects the text indexes into.
        effects: Every skill effect row, keyed by id.

    Returns:
        The description with each resolvable placeholder replaced by its base value.
    """
    links = LIST_ENTRY.findall(card.get("link_skill_eff_id") or "")

    def replace(match):
        column = card_value_field(match.group(1))
        index = int(match.group(2))
        if column is None or index >= len(links):
            return match.group(0)
        effect = effects.get(links[index]) or {}
        value = effect.get(column)
        if not value:
            return match.group(0)
        return value + "%" if needs_percent(effect, column, text, match.end()) else value

    return CARD_PLACEHOLDER.sub(replace, text)


def resolve_relic_values(text, relic):
    """Fill an equipment placeholder in from the values on its own row.

    Args:
        text: The raw description.
        relic: The relic's row.

    Returns:
        The description with each resolvable placeholder replaced by its base value.
    """
    def replace_from(values):
        def replace(match):
            index = int(match.group(1))
            return values[index] if index < len(values) else match.group(0)
        return replace

    text = RELIC_PLACEHOLDER.sub(replace_from(LIST_ENTRY.findall(relic.get("s1_cs_value") or "")), text)
    return RELIC_NB_PLACEHOLDER.sub(replace_from(LIST_ENTRY.findall(relic.get("s1_nb_eff_value") or "")), text)


def clean_description(text, table):
    """Turn one resolved description into the plain sentence a tooltip can show.

    Args:
        text: The description, with values already filled in.
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


# What the client calls each rarity, and the short name used here. Anything not listed is ignored, which
# keeps a future rarity from silently reading as the best one.
RARITIES = {
    "RARITY_COMMON": "COMMON",
    "RARITY_RARE": "RARE",
    "RARITY_LEGEND": "LEGEND",
    "RARITY_UNIQUE": "UNIQUE",
}
# Equipment slots, in the order `_EQUIPMENT_TYPE_SLOTS` numbers them: attack, defense, health.
SLOTS = {"EQUIP_WEAPON": 0, "EQUIP_ARMOR": 1, "EQUIP_ACC": 2}
# Which classes may hold a card. Empty for nine cards in ten, and it is a class rather than a combatant, so
# it can only ever answer "could anyone on this team use this", never "whose is it".
CARD_CLASS_COLUMN = "ownable_link_base_class_define_id"
COMBATANT_CLASS_COLUMN = "link_base_class_define_id"
# Only the player card tables. The broader `*card.json` glob also picks up 1,790 monster card rows that carry
# no rarity at all, and because a name is resolved to its shortest id, one of those can displace the real card
# and take its rarity with it.
PLAYER_CARD_TABLES = ("card(*)@card.json", "rarity")


def id_list(value):
    """Read one of the dump's bracketed id lists.

    The dump writes an empty list as the two-character string `[]`, which is why a plain truth test on these
    columns reports every row as populated. Parsing it properly is the difference between "every equipment
    names a combatant" and the truth, which is that none of them do.

    Args:
        value: The raw column value, such as `[psionic,controller]` or `[]`.

    Returns:
        A tuple of ids, empty when the column holds none.
    """
    inner = str(value or "").strip().strip("[]")
    return tuple(part.strip() for part in inner.split(",") if part.strip())


def collect_quality(table, dump_dir):
    """Pair every card, equipment and combatant with what the client knows about its worth.

    Args:
        table: The localization table.
        dump_dir: Path to the dump's `output` directory.

    Returns:
        A dict of constant name to value, ready to render.
    """
    cards = base_rows_by_name(load_data_tables(dump_dir, PLAYER_CARD_TABLES), table)
    relics = base_rows_by_name(load_data_tables(dump_dir, RELIC_TABLES), table)

    card_rarity = {}
    card_classes = {}
    for name, row in cards.items():
        rarity = RARITIES.get(row.get("rarity"))
        if rarity:
            card_rarity[name] = rarity
        classes = id_list(row.get(CARD_CLASS_COLUMN))
        if classes:
            card_classes[name] = classes

    equipment_rarity = {}
    equipment_slot = {}
    for name, row in relics.items():
        rarity = RARITIES.get(row.get("rarity"))
        if rarity:
            equipment_rarity[name] = rarity
        slot = SLOTS.get(row.get("relic_type"))
        if slot is not None:
            equipment_slot[name] = slot

    combatant_class = {}
    for row in json.loads(Path(dump_dir, "db", COMBATANT_TABLE).read_text(encoding="utf-8")):
        name = (table.get(COMBATANT_NAME_ID.format(id=row.get("id"))) or "").strip()
        klass = str(row.get(COMBATANT_CLASS_COLUMN) or "").strip()
        if name and klass and klass != "none":
            combatant_class[name] = klass

    return {
        "CARD_RARITY": card_rarity,
        "CARD_CLASSES": card_classes,
        "EQUIPMENT_RARITY": equipment_rarity,
        "EQUIPMENT_SLOT": equipment_slot,
        "COMBATANT_CLASS": combatant_class,
    }


def render_quality(quality, dump_dir):
    """Write the module holding what each card and equipment is worth.

    Args:
        quality: The collected mappings.
        dump_dir: Path to the dump, recorded in the header.

    Returns:
        The module source.
    """
    comments = {
        "CARD_RARITY": "What the client grades each card, for deciding whether one is worth buying or keeping.",
        "CARD_CLASSES": "Which classes may hold a card, for the roughly one card in ten that is restricted."
                        " A card absent from here is unrestricted, and the value is a class, not a combatant.",
        "EQUIPMENT_RARITY": "What the client grades each piece of equipment.",
        "EQUIPMENT_SLOT": "Which of the three equipment slots a piece goes in, numbered as the handlers number them.",
        "COMBATANT_CLASS": "Each combatant's class, so a team read off the Combatants screen becomes a set of classes.",
    }
    lines = [
        '"""What the client knows about the worth of a card, a piece of equipment, or a combatant.',
        "",
        "Generated by `scripts/build_game_data.py` - do not edit by hand. Re-run it after a game patch.",
        "",
        "Only what the dump actually carries is here. In particular there is no per-combatant link for either",
        "cards or equipment: the equipment column that looks like one is empty on every row, and the card column",
        "is empty on nine rows in ten and names a class rather than a combatant on the rest.",
        "",
        SOURCE_NOTE,
        f"Generated: {date.today().isoformat()}",
        '"""',
        "",
    ]
    for name, values in quality.items():
        lines.append("")
        lines.append(f"# {comments[name]}")
        lines.append(f"{name} = {{")
        for key in sorted(values):
            lines.append(f"    {key!r}: {values[key]!r},")
        lines.append("}")
    return chr(10).join(lines) + chr(10)


def base_rows_by_name(rows, table):
    """Pick one row per name, preferring the base version of a card over its upgrades.

    A card appears once per upgrade tier, all under the same name and all with ids that extend the base one,
    so the shortest id is the version to describe.

    Args:
        rows: Data rows keyed by id, each carrying a `name` localization key.
        table: The localization table.

    Returns:
        A dict of English name to row.
    """
    chosen = {}
    for row_id, row in rows.items():
        name = table.get(row.get("name") or "")
        if name and (name not in chosen or len(row_id) < len(chosen[name][0])):
            chosen[name] = (row_id, row)
    return {name: row for name, (_, row) in chosen.items()}


def collect_descriptions(table, dump_dir):
    """Pair every named card and equipment with its effect text, values filled in.

    Args:
        table: The localization table.
        dump_dir: Path to the dump's `output` directory.

    Returns:
        A dict of entity name to cleaned description.
    """
    effects = load_data_tables(dump_dir, EFFECT_TABLES)
    sources = [
        (load_data_tables(dump_dir, CARD_TABLES), "desc", lambda raw, row: resolve_card_values(raw, row, effects)),
        (load_data_tables(dump_dir, RELIC_TABLES), "s1_description", resolve_relic_values),
    ]

    described = {}
    for rows, description_key, resolve in sources:
        for name, row in base_rows_by_name(rows, table).items():
            raw = table.get(row.get(description_key) or "")
            if not raw:
                continue
            body = clean_description(resolve(raw, row), table)
            # A description that only repeats the name tells the user nothing the tooltip does not already show.
            if not body or body == name:
                continue
            if name in described and described[name] != body:
                print(f"  note: '{name}' is named by two tables, keeping the first description")
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
        SOURCE_NOTE,
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
        SOURCE_NOTE,
        f"Generated: {date.today().isoformat()}",
        '"""',
        "",
        "# Keyed by the same names as the rosters in `game_data.py`. Numbers are the card's base values, before",
        "# any scaling the run applies. A stray `X` is a value that lives in a table the generator does not read.",
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
    described = collect_descriptions(table, args.dump)
    quality = collect_quality(table, args.dump)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(groups, args.dump), encoding="utf-8")
    OUT_TEXT_PATH.write_text(render_descriptions(described, args.dump), encoding="utf-8")
    OUT_QUALITY_PATH.write_text(render_quality(quality, args.dump), encoding="utf-8")

    unresolved = sum(1 for text in described.values() if VALUE_PLACEHOLDER in text)
    print(f"read {len(table)} localization rows from {args.dump}")
    for name, values, _ in groups:
        with_text = sum(1 for value in values if value in described)
        print(f"  {name:12} {len(values):5d}   {with_text:5d} described")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {OUT_TEXT_PATH.relative_to(REPO_ROOT)} with {len(described)} descriptions, "
          f"{unresolved} of them still holding an unresolved value")
    print(f"wrote {OUT_QUALITY_PATH.relative_to(REPO_ROOT)} with "
          + ", ".join(f"{len(values)} {name.lower()}" for name, values in quality.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
