"""Grade cards, equipment and combatants from the client's own data.

Names are folded before matching, because neither the reader nor the client spells them predictably.

`suits` is the one judgement here that is about a pairing rather than a thing. The game keeps an opinion on
which equipment suits which combatant - it labels equipment with the kind of deck it serves, and gives each
combatant a weight per kind - but only fills that in for Sortie, so `game_quality.py` carries it across to
the Chaos copies of the same relics and `hand_tags.py` fills the gaps that leaves by reading the effect text.

It still only ever orders pieces that rarity has already ranked equal, and never promotes one above a better
piece. That is not caution about coverage: upstream treats the priority list as an override rather than a
tiebreak, so a well-suited Legend ranked above an ill-suited Unique would have the run strip the Unique it is
already wearing to install the Legend.
"""

import re
from collections import Counter

from ok import Logger

from src.en.game_quality import (
    CARD_CLASSES, CARD_RARITY, COMBATANT_CLASS, COMBATANT_TAG_WEIGHTS, EQUIPMENT_RARITY, EQUIPMENT_SLOT,
    EQUIPMENT_TAGS,
)
from src.en.hand_tags import HAND_TAGS

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

# Everything that is not a letter, a digit or one of the geometric shapes. Apostrophes, hyphens, spaces and
# the zero-width space the client hides in one card name all disappear, which is what makes a concatenated
# OCR reading match. The shapes are kept because one real card is named `○ △ □` and nothing else -
# without them it folds away to nothing, and then every punctuation-only box the reader produces folds to
# the same nothing and matches it.
INSIGNIFICANT = re.compile(r"[^0-9a-z一-鿿■-◿]+")

# Characters the reader hands back for one another, grouped by what they look like on screen. The first of
# each group is the spelling the rest fold into. Only what the logs actually show being swapped is here, and
# a capital I read as a lowercase l is far the commonest of them - `Magic-lnfused Sapphire`, `Instinct
# lgnition`, `Mutation: lron Wall` are all real readings. Letters that would turn one real word into another
# are deliberately absent: reading v as m or r as f would quietly match the wrong name, and a wrong match is
# worse than any number of missed ones.
CONFUSABLE = {letter: group[0] for group in ("il1", "o0", "s5", "gq9", "b6", "z2") for letter in group}


def fold(name):
    """Reduce a name to the form used for matching.

    Args:
        name: A card, equipment or combatant name, from either the client's data or the reader.

    Returns:
        The name, lower cased with punctuation and spacing removed.
    """
    return INSIGNIFICANT.sub("", (name or "").casefold())


def unconfused(folded):
    """Rewrite the characters the reader swaps for one another into one spelling each.

    Args:
        folded: A name that has been through `fold`.

    Returns:
        The same name with every lookalike character replaced by the one standing for its group.
    """
    return "".join(CONFUSABLE.get(character, character) for character in folded)


def sorted_letters(folded):
    """Reduce an already-folded name to its letters in order, so word order stops mattering.

    Args:
        folded: A name that has been through `fold`.

    Returns:
        The same characters, sorted.
    """
    return "".join(sorted(folded))


# The spellings a reading is retried under, in falling order of how much of it they take on trust. Sorting
# comes last because it throws away the order, and it is applied to the unconfused form so a name that was
# both misread and scrambled still lands.
FALLBACK_SPELLINGS = (unconfused, lambda folded: sorted_letters(unconfused(folded)))


def index(names):
    """Build a folded lookup for a set of names.

Several keys per name where it is safe to have them: the folded name first, then one per fallback spelling.
    The reader mangles a name in two ways that keep all of its letters - it swaps lookalike characters, and it
    hands the words back out of order - so `Magic-Infused Sapphire` arrives as `Magic-lnfusedSapphire` and
    `Assault Gauntlets` as `GauntletsAssault`. Both were simply lost before. A fallback key is only added
    where exactly one name owns it and nothing nearer has claimed it, so names that would collide keep their
    exact spellings and answer to nothing else.

    Args:
        names: An iterable of canonical names.

    Returns:
        A dict of key to canonical name. A name that folds away to nothing is left out, since that key would
        match every reading made only of characters the fold discards.
    """
    exact = {folded: name for folded, name in ((fold(name), name) for name in names) if folded}
    lookup = dict(exact)
    for spell in FALLBACK_SPELLINGS:
        owners = Counter(spell(folded) for folded in exact)
        for folded, name in exact.items():
            key = spell(folded)
            # Never over a key already claimed: an exact spelling, and then a nearer guess, both outrank this.
            if owners[key] == 1 and key not in lookup:
                lookup[key] = name
    return lookup


def look_up(name, lookup):
    """Find the client's own spelling of a name the reader produced.

    Tried in order of how much of the reading each spelling trusts: the reading as it stands, then with
    lookalike characters put right, then with the words allowed to have come back in any order.

    Args:
        name: The name as read off the screen.
        lookup: A folded index from `index`.

    Returns:
        The canonical name, or None when nothing in the index answers to it.
    """
    folded = fold(name)
    for spell in (str, *FALLBACK_SPELLINGS):
        found = lookup.get(spell(folded))
        if found is not None:
            return found
    return None


# The game's own labels, with the hand-read ones filling the gaps it left. The generated half wins wherever
# both speak, since it is the developers' answer and the other is a reading of the effect text.
TAGS = {**HAND_TAGS, **EQUIPMENT_TAGS}

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
    canonical = look_up(name, lookup)
    if canonical is None:
        return None
    return canonical, table[canonical]


def wants(combatant):
    """Read the kinds of equipment a combatant is said to want.

    Args:
        combatant: The combatant's name, in any spelling.

    Returns:
        A dict of equipment kind to the weight this combatant puts on it, empty when the data has no opinion
        about them at all.
    """
    return COMBATANT_TAG_WEIGHTS.get(look_up(combatant, COMBATANT_INDEX)) or {}


def tallied(equipment, weights):
    """Add up what one combatant's weights say about one piece of equipment.

    Args:
        equipment: The equipment's name as the client spells it, or None when it is not known equipment.
        weights: That combatant's weights, from `wants`.

    Returns:
        The total weight, zero when either side carries nothing.
    """
    return sum(weights.get(tag, 0) for tag in TAGS.get(equipment) or ())


def suits(equipment_name, combatant):
    """Say how much a piece of equipment suits the combatant who would wear it.

    Args:
        equipment_name: The equipment name as read off the screen, in any spelling.
        combatant: The combatant's name, in any spelling.

    Returns:
        The weight that combatant puts on the kinds this piece serves, on the game's own scale. Zero when
        either side carries nothing, which reads as "no opinion" rather than as "unsuitable".
    """
    return tallied(look_up(equipment_name, EQUIPMENT_INDEX), wants(combatant))


def worth_taking(names, classes=(), cards=True, suited_to=None):
    """Pick out the names worth spending on, best first.

    Args:
        names: Candidate names as read off the screen, which may be concatenated or misspelt.
        classes: The team's classes, used to skip cards nobody could hold.
        cards: True to grade against cards, False for equipment.
        suited_to: The combatant who would wear the equipment, used to order pieces of equal rarity. None
            leaves the order exactly as it was.

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
    # Only equipment carries the tags, and only within one rarity, so a preference can never talk the run
    # into a worse piece than it would have bought anyway. The combatant is the same for every name here, so
    # their weights are read once rather than per name, and `found` already holds the client's own spelling.
    weights = {} if cards else wants(suited_to)
    return sorted(found, key=lambda name: (WORTH_TAKING.index(found[name]), -tallied(name, weights), name))


def slot_of(name):
    """Say which equipment slot a piece fills.

    Args:
        name: The equipment name as read off the screen.

    Returns:
        The slot index, or None when the name is not known equipment.
    """
    return EQUIPMENT_SLOT.get(look_up(name, EQUIPMENT_INDEX))
