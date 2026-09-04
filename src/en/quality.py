"""Grade cards, equipment and combatants from the client's own data.

Names are folded before matching, because neither the reader nor the client spells them predictably.
"""

import re

from ok import Logger

from src.en.game_quality import CARD_CLASSES, CARD_RARITY, COMBATANT_CLASS, EQUIPMENT_RARITY, EQUIPMENT_SLOT

logger = Logger.get_logger(__name__)

# Grades worth spending on, best first. Rare is deliberately excluded: it is the bulk of what a shop offers,
# and buying it is how you end a run with no Credits and nothing to show.
WORTH_TAKING = ("UNIQUE", "LEGEND")

# The client's internal class ids, and what the game calls them on screen. Only one differs, but it is the
# one that matters: a combatant the game calls a Vanguard is a "knight" in the data.
CLASS_NAMES = {
    "striker": "Striker",
    "knight": "Vanguard",
    "ranger": "Ranger",
    "hunter": "Hunter",
    "psionic": "Psionic",
    "controller": "Controller",
}

# Everything that is not a letter or a digit. Apostrophes, hyphens, spaces and the zero-width space the
# client hides in one card name all disappear, which is what makes a concatenated OCR reading match.
INSIGNIFICANT = re.compile(r"[^0-9a-z一-鿿]+")


def fold(name):
    """Reduce a name to the form used for matching.

    Args:
        name: A card, equipment or combatant name, from either the client's data or the reader.

    Returns:
        The name, lower cased with punctuation and spacing removed.
    """
    return INSIGNIFICANT.sub("", (name or "").casefold())


def index(names):
    """Build a folded lookup for a set of names.

    Args:
        names: An iterable of canonical names.

    Returns:
        A dict of folded name to canonical name.
    """
    return {fold(name): name for name in names}


CARD_INDEX = index(CARD_RARITY)
EQUIPMENT_INDEX = index(EQUIPMENT_RARITY)
COMBATANT_INDEX = index(COMBATANT_CLASS)


def team_classes(names):
    """Turn the combatants on screen into the set of classes they cover.

    Args:
        names: Combatant names as read from the Combatants screen.

    Returns:
        The set of class ids, empty when none were recognised.
    """
    classes = set()
    for name in names:
        canonical = COMBATANT_INDEX.get(fold(name))
        if canonical:
            classes.add(COMBATANT_CLASS[canonical])
    return classes


def named(classes):
    """Say a set of classes the way the game does.

    Args:
        classes: Internal class ids.

    Returns:
        The in-game names, sorted, so a log line reads in the player's terms.
    """
    return sorted(CLASS_NAMES.get(klass, klass) for klass in classes)


def usable_by(card_name, classes):
    """Report whether anyone on the team could hold a card.

    Args:
        card_name: The canonical card name.
        classes: The team's classes, as `team_classes` returns them.

    Returns:
        True when the card is unrestricted, when its classes overlap the team's, or when the team is unknown.
    """
    restricted_to = CARD_CLASSES.get(card_name)
    if not restricted_to or not classes:
        return True
    return bool(set(restricted_to) & classes)


def grade(name, table, lookup):
    """Look a name up in one of the client's grade tables.

    Args:
        name: The name as read off the screen.
        table: The grade table to read.
        lookup: The folded index for that table.

    Returns:
        A `(canonical_name, grade)` pair, or None when the name is not in the table.
    """
    canonical = lookup.get(fold(name))
    if canonical is None:
        return None
    return canonical, table[canonical]


def worth_taking(names, classes=(), cards=True):
    """Pick out the names worth spending on, best first.

    Args:
        names: Candidate names as read off the screen, which may be concatenated or misspelt.
        classes: The team's classes, used to skip cards nobody could hold.
        cards: True to grade against cards, False for equipment.

    Returns:
        The canonical names worth taking, Unique before Legend, each appearing once.
    """
    table, lookup = (CARD_RARITY, CARD_INDEX) if cards else (EQUIPMENT_RARITY, EQUIPMENT_INDEX)
    found = {}
    for name in names:
        graded = grade(name, table, lookup)
        if graded is None:
            continue
        canonical, rarity = graded
        if rarity not in WORTH_TAKING:
            continue
        if cards and not usable_by(canonical, classes):
            logger.info(f"skipping {canonical}, a {rarity} card no one on this team can hold")
            continue
        found[canonical] = rarity
    return sorted(found, key=lambda name: (WORTH_TAKING.index(found[name]), name))


def slot_of(name):
    """Say which equipment slot a piece fills.

    Args:
        name: The equipment name as read off the screen.

    Returns:
        The slot index, or None when the name is not known equipment.
    """
    canonical = EQUIPMENT_INDEX.get(fold(name))
    return EQUIPMENT_SLOT.get(canonical) if canonical else None
