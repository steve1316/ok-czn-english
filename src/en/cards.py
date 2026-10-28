"""Decide which cards to play in a Sortie battle, and in what order.

Sortie has no Auto button, so the bot picks every card itself. Upstream looks each hand card up in a list of
names the user typed and plays the first match, but that list starts empty on the Global client - its default
is Chinese card names English OCR can never match - so every turn falls through to pressing each hotkey and
hoping. This module replaces the hoping.
"""

import re
from collections import Counter, namedtuple
from functools import lru_cache
from itertools import combinations

from src.en.game_battle import CARD_CATEGORY, CARD_COST, CARD_OWNER, COMBATANT_ATTRIBUTE, X_COST
from src.en import kits
from src.en.game_text import DESCRIPTIONS
from src.en.kits.kit import (ATTACK_CATEGORY, PHASE_ATTACK, PHASE_EPIPHANY, PHASE_ESCAPE, PHASE_FREE, PHASE_OTHER, PHASE_PRIME, PHASE_SETUP,
                             PHASE_SPENDS_EVERYTHING, base_name)
from src.en.quality import fold, in_order, index, one_edit_apart, unconfused

# Action Points a turn starts with, before anything in a run changes the figure.
BASE_ACTION_POINTS = 3
# `X_COST` comes from the generated data rather than being restated here, so a card that spends everything
# left cannot come to mean one thing to the generator and another to this.
# Categories the game deals you rather than ones you choose. A Curse is someone else's doing and a Status
# Ailment is damage waiting to happen, so neither is ever part of a plan.
DEALT_TO_YOU = frozenset({"ABNORM", "CURSE"})
# One of those that does its harm only while held - "If in hand, at the end of the turn", "If this card is in hand",
# a "Retain:" line - so playing it is how to be rid of it.
HELD_HARM = re.compile(r"\b(?:if|when) (?:this card is )?in hand|if the turn ends when in hand|when this card is retained|^Retain:", re.I | re.M)
# Any effect a card's text can carry names a number, so a text without one - blank, or flavour - does nothing when played.
INERT_EFFECT = re.compile(r"\d")
# A card of your own that works just by being held, as Unknown: Mutant Sample's "If in hand, +40% Damage Amount".
# It shows no cost and cannot be played.
HELD_HELP = re.compile(r"^If (?:this card is )?in hand,", re.I)
# A line the generator marks as firing when the card is kept in hand at the end of the turn, which playing it never does.
RETAIN_LINE = re.compile(r"^Retain:.*\n?", re.M)
# A card that only makes other cards better, so it wants to land before them.
SETUP_CATEGORY = "POWER"
# What a card the data has never heard of is assumed to cost. One is both the commonest price and the
# forgiving guess: too low only risks a card that will not play, while too high would refuse it outright.
ASSUMED_COST = 1

# What a combatant's cards turn into on a Mental Breakdown at max Stress. They are free, playing them is how the combatant recovers, and
# Fear's unexpected result can end the fight outright, so they are tried before anything else is spent.
BREAKDOWN_CARDS = frozenset({"Confusion", "Impulse", "Guilt", "Daze", "Escapism", "Gloom", "Charm", "Trance", "Fear", "Despair"})

# Roughly what one drawn card is worth, said in damage. A card drawn is about one more card played, and the
# ordinary card costing one point does 100% damage, so that is the exchange rate the data itself suggests.
DRAW_VALUE = 100
# Shield keeps a combatant standing but does not end the fight, so the same number is worth less than damage.
SHIELD_WEIGHT = 0.6
# What matching the attribute an enemy is weak to is worth. The game pays a match in extra damage and in
# extra Tenacity damage both, so a matching card is worth more than the figure printed on it.
WEAKNESS_BONUS = 1.5
# What a card is worth when its effect text says nothing measurable - an Immunity, a Morale, a status with no
# figure on it. Rating those zero would mean a buff never got played at all, which is worse than the guess.
# The ordinary card costing one point does 100% damage, so an unreadable effect is priced at the same rate.
UNREAD_VALUE = 100
# What a card lit up for an Epiphany is worth beyond what it does this turn. The upgrade is permanent and the
# run is long, so it comfortably outweighs one turn of anything.
EPIPHANY_BONUS = 1000

# A damage figure is a percentage followed shortly by the word Damage. "Damage Amount" is excluded on purpose:
# that phrasing is always a modifier on some other card's damage, as in "Increases Damage Amount by 20%", and
# counting it would rate a card that does nothing by itself as though it hit hard. A hit count after it, as in
# "40% Damage x 3", or right after the percentage, as in "60% x 3 Damage", multiplies the figure. The client mostly
# writes a multiplication sign, and a few cards a plain x.
DAMAGE = re.compile(r"(\d+)%(?:\s*[×x]\s*(\d+))?[^\n]{0,24}?Damage(?!\s+Amount)(?:\s*[×x]\s*(\d+))?")
SHIELD = re.compile(r"(\d+)%[^\n]{0,20}?Shield")
DRAW = re.compile(r"\bDraw (\d+)")
# A line of damage that lands on every enemy, as in Vulture Ejection's "120% Defense-Based Damage to all enemies". The data's own target
# misses some, Diagonal Slash among them. "To random enemies" spreads its hits instead, so that stays one target's worth.
ALL_ENEMIES = re.compile(r"\bto all enemies\b")
# A card that makes the next attack hit harder, or the target take more - "Add 1 Hit(s) to the next Attack Card", "+X% Damage
# Amount to the next Bullet card", "2 Vulnerable". Played after the attacks, as its category alone left it, it lands on nothing.
PRIME = re.compile(r"(?:Damage Amount|Hit\(s\)|Proc)[^|\n]*?\bnext\b[^|\n]*?\b(?:Attack|Bullet|Bind) Card"
                   r"|(?:\b\d+ Vulnerable|Vulnerable \d+)(?! to (?:allies|self))|Damage Amount taken by the target", re.I)

# How many copies of each version of a card the deck holds, by canonical name: the last `piles` read, and every change `piles` saw since.
COPIES = {}
# The effect text of every card in `COPIES`, by canonical name: the Epiphany it carries, the weakest where copies differ.
# Mutated in place, never rebound, and empty until a read, so every card falls back to its base text.
DECK = {}

# What a card does, in the terms the ordering cares about.
Features = namedtuple("Features", [
    # Damage to one enemy, as a percentage with every hit added up.
    "damage",
    # Shield, as a percentage.
    "shield",
    # Cards drawn.
    "draw",
    # The part of `damage` that lands on every enemy rather than one.
    "spread",
], defaults=[0])
# What the picker knows about the moment it is choosing in.
Board = namedtuple("Board", [
    # Action Points to plan against.
    "action_points",
    # The attribute the enemies are weak to, which `board.weakness` reads off the badge beside each enemy's action counter.
    "weakness",
    # The hand card the run has lit up. Nothing reads it yet - no capture holds one to pin the region against - so it is None.
    "epiphany",
    # Every card in hand as canonical names, for the kits. Empty means `plan` fills it from the hand it is given.
    "hand",
    # Canonical names of the cards the game took this turn, oldest first, for kits that count what has been played.
    "played",
    # The same for the turn before, which is empty on a battle's first turn.
    "last_turn",
    # The hand size the hand counter reads, which is more than `hand` when OCR missed a card. 0 when not known.
    "hand_size",
    # Canonical names of the cards still in hand when the turn before ended, so their Retain effects have fired.
    "kept",
    # Canonical card name to the text of the version the deck holds, for kits whose rule rests on one Epiphany. `DECK` itself, so it sees every read.
    "deck",
    # Whether an enemy shows Absolute Invincibility, from `board.enemy_invulnerable`, so damage is worth nothing this turn.
    "invulnerable",
    # How many enemies are on screen, from `board.enemy_counters`, so damage to all enemies counts once for each. 1 when not known.
    "enemies",
], defaults=[BASE_ACTION_POINTS, None, None, (), (), (), 0, (), DECK, False, 1])

# How many distinct readings to remember the folding of. OCR invents new misspellings all session, so this
# is bounded rather than unlimited, and it is far larger than the ten names one frame ever asks about.
CACHED_READINGS = 1024
# Folded card name to the client's own spelling, so a reading run together or in the wrong case still lands.
CARD_INDEX = index(CARD_COST)

# The type label the game prints under every card, in both the English the Global client draws and the
# Chinese `ocr.po` rewrites some of them into. Upstream's own filter lists only Chinese, so every English
# label reached the hand as a card name - `Basic Atta` was the commonest junk reading in a Chaos recording.
# `Defense` is here because the catalog does rewrite it, to a literal upstream's exclude list never had.
# The level badge an upgraded card carries is read the same way, as "@ Lv." or as the 等级 `ocr.po` rewrites "LV" to.
TYPE_LABELS = ("basic attack", "basic skill", "status ailment", "attack", "skill", "curse", "power",
               "upgrade", "defense", "攻击力", "防御力", "状态异常", "lv", "等级")
FOLDED_LABELS = tuple(fold(label) for label in TYPE_LABELS)
# The label under every Mental Breakdown card, matched only on a run of 7 of its letters. The rules for the short labels would eat real
# cards cut short: "Accent" is Mute Accent and one edit from "Ment", and "Down" is Downward Cut. No card name holds any of these runs.
BREAKDOWN_PIECES = frozenset(fold("Mental Breakdown")[start:start + 7] for start in range(len(fold("Mental Breakdown")) - 6))
# The type icon shares the label's OCR box and is read as a stray letter or two in front of it, which is why
# `XBasic A` occurs. `src/en/ocr_text.py` trims the same way for the same reason.
LABEL_PREFIX = 2
# The shortest piece from inside a label, rather than its start, taken for that label - "tack", "grade" and "pgrad" are real readings.
LABEL_PIECE = 4
# How much of a name has to survive before a truncated reading is worth repairing. Below this a stub matches
# too many cards to mean anything - four would rescue only two more readings out of 1,662 and risk far more.
MIN_STUB = 5
# How many letters at the end of a name cut short may be wrong. The reader mangles the letter it cut at, as in "Quantun",
# "Barrier Der" and "Fairy's Prc", so a stub that fits nothing is retried with up to this many dropped.
GARBLED_TAIL = 2
# How much of a name a reading checked against the deck has to keep, as a share of its letters. Live, Annihilation came back as
# "DarkMistSecretAil", 17 of 29, far past what the whole roster can risk but the only Dark Mist card those letters fit in that deck.
DECK_SHARE = 0.5
# Tiphera's three Archetype cards differ only by a glyph the reader seldom keeps - "Archetype:O", "Archetyp", "rchetype:".
# Matched on folded text, on a piece of the word, with a real glyph or the O, C or 0 the reader takes the circle for at the end.
ARCHETYPE_READ = re.compile(r"(?:rchet|het[yv]p)[a-z]*?([○△□oc0]?)$|^arche$")
ARCHETYPES = {"△": "Archetype: △", "□": "Archetype: □"}
# All three cost nothing, so which one a reading that lost its glyph is taken for changes how it ranks, never whether it is played.
ARCHETYPE_UNREAD = "Archetype: ○"
# The keyword tags a card's tooltip lists, like "[Unique / Bullet]", which the reader picks up when the tooltip covers the hand.
# No card name holds a bracket or a slash.
KEYWORD_TAG = re.compile(r"[\[\]/]")


def looks_like_label(folded):
    """Say whether a reading is a type label, read whole, cut short or a letter wrong.

    Args:
        folded: The reading, already folded, maybe with the type icon read as a letter or two in front.

    Returns:
        True when it is a label, the start of one or a piece from inside one, give or take one letter.
    """
    if any(piece in folded for piece in BREAKDOWN_PIECES):
        return True
    for trimmed in (folded[cut:] for cut in range(LABEL_PREFIX + 1)):
        if not trimmed:
            continue
        for label in FOLDED_LABELS:
            start = label[:len(trimmed)]
            if trimmed == start or one_edit_apart(trimmed, start) or one_edit_apart(trimmed, label) or (len(trimmed) >= LABEL_PIECE and trimmed in label):
                return True
    return False


def owner(name):
    """Name the combatant a card belongs to.

    Args:
        name: A card name the data knows, in any Epiphany.

    Returns:
        The combatant, or None for a card no combatant owns.
    """
    return CARD_OWNER.get(base_name(name))


def stub_card(stub, party=frozenset()):
    """Find the one card a name cut short can be.

    The reader cuts from either end - "Knife Tos" and "rrier Der" are both real readings - so a stub is tried as the start
    of a name and then as a piece of one. Two cards that fit means the reading cannot say which, and a shorter stub only fits more.
    A reading that looks like a label only gets the first try, so "Quant" is still Quantum Seed but "XAttacl" finds no card.
    Since we know who is in the party, a fit owned by any other combatant cannot be in hand, which narrows the lookup to the cards
    this party can hold - "ord Slas" fits Rossweisse's Sword Slash and Yuki's Longsword Slash, and only one of them is in a party.

    Args:
        stub: A folded reading the index has no spelling for.
        party: The combatants known to be in the party. Empty when none are known yet, which leaves every card in play.

    Returns:
        The card, or None when nothing or more than one card fits. A card and its Epiphanies count as one card, the plainest of them.
    """
    tries = [(cut, fits) for cut in range(GARBLED_TAIL + 1) for fits in (str.startswith, str.__contains__)]
    for cut, fits in tries[:1] if looks_like_label(stub) else tries:
        piece = stub[:len(stub) - cut]
        if len(piece) < MIN_STUB:
            return None
        # Over the exact spellings only: the fallback spellings in the index rearrange or rewrite letters, so a piece of one means nothing.
        matches = [real for folded, real in CARD_INDEX.exact.items() if fits(folded, piece)]
        # Kept whole when no fit is the party's, so a member whose cards have not been read yet still gets the old answer.
        if party:
            matches = [real for real in matches if owner(real) in (None, *party)] or matches
        if matches:
            return min(matches, key=len) if len({base_name(real) for real in matches}) == 1 else None
    return None


@lru_cache(maxsize=CACHED_READINGS)
def canonical(name, party=frozenset(), deck=frozenset()):
    """Turn a name as read off the screen into the one the data is keyed by.

    Args:
        name: The card name the reader produced.
        party: The combatants known to be in the party, which settles a name cut short that fits cards of several combatants.
        deck: The canonical names of the cards the deck holds, from `DECK`, for a hand card too garbled for the whole roster.

    Returns:
        The client's spelling, or the name unchanged when nothing matches it.
    """
    # The hotkey sits just above the card name, close enough that the reader sometimes returns the two as one
    # box - a real hand came back as "1=Soul Riff". No card in the data is named starting with a digit, so a
    # leading one is the key rather than part of the name. It comes off before anything else, because the
    # looser spellings read a 1 as a letter and would land "1Homing Laser" on "Homing Laser L".
    stub = fold(name).lstrip("0123456789")
    known = CARD_INDEX.look_up(stub)
    if known:
        return known
    # The reader also cuts a name short while the hand animates, so "Knife Tos" arrives for "Knife Toss".
    # Only an unambiguous stub is repaired: two cards start "Attac", and guessing between them would be
    # worse than leaving the reading alone for the label test to deal with.
    known = stub_card(stub, party) or deck_card(stub, deck)
    if known:
        return known
    archetype = ARCHETYPE_READ.search(stub)
    if archetype:
        return ARCHETYPES.get(archetype.group(1) or "", ARCHETYPE_UNREAD)
    return name


def deck_card(stub, deck):
    """Find the one card the deck holds whose letters a garbled reading keeps in order.

    Args:
        stub: A folded reading neither the index nor `stub_card` could place.
        deck: The canonical names of the cards the deck holds. Empty before the piles are read, which finds nothing.

    Returns:
        The card, or None when no card or more than one fits, or the reading keeps less than `DECK_SHARE` of the name.
    """
    if len(stub) < MIN_STUB or looks_like_label(stub):
        return None
    # Lookalikes folded on both sides, since "Mutation:Forbidden AIgorthm" keeps every letter in order but one capital I.
    matches = [real for real in deck if len(stub) >= len(fold(real)) * DECK_SHARE and in_order(unconfused(stub), unconfused(fold(real)))]
    return min(matches, key=len) if matches and len({base_name(real) for real in matches}) == 1 else None


def is_card_name(reading):
    """Say whether a reading off the hand names a card, or is the type label printed under one.

    A name the data knows always wins, because several real cards are named after a label - `Attack!`,
    `Curse of the Fairy`, `Defense System`, `Power Anchor`. Testing the label first would delete all of them.
    A reading the data does not know is kept unless it looks like a label, so a card released after the dump
    is still played rather than silently dropped.

    Args:
        reading: The text the reader returned for one hand card.

    Returns:
        True when it should be treated as a card.
    """
    folded = fold(reading)
    if not folded or KEYWORD_TAG.search(reading):
        return False
    # Two real cards are named exactly after a label, `Attack!` and `Curse`. `ocr.po` already ruled on both:
    # the label appears under every card of that type while the card is one of 794, so the label wins. Curse
    # cards are never played voluntarily anyway, which leaves `Attack!` as the whole cost of the rule.
    if folded in FOLDED_LABELS:
        return False
    known = canonical(reading)
    # A label misread by one letter lands on `Attack!` too, so the same ruling covers it. Live, "Attacl" under
    # Cobalt Light was played as `Attack!` and pressed Cobalt Light's key in its place.
    if fold(known) in FOLDED_LABELS:
        return False
    return known in CARD_COST or not looks_like_label(folded)


def features(name):
    """Read what a card does out of its own effect text.

    The text is the client's, written for a player rather than for a parser, so this reads the parts that are
    stated plainly and ignores the rest. A card whose effect is conditional reads as zero, which costs it
    position within its phase but never keeps it out of a plan.

    Args:
        name: The card name, in any spelling.

    Returns:
        The `Features` the text states, all zero for a card with no description.
    """
    return parsed(canonical(name))


@lru_cache(maxsize=None)
def parsed(name):
    """Pull the figures out of one card's effect text.

    Cached on the client's own spelling rather than on what was read off the screen, so the cache is bounded
    by the catalog instead of by however many ways OCR has misread a name over a long session.

    Args:
        name: The canonical card name.

    Returns:
        The `Features` the text states.
    """
    return figures(text_of(name))


def damage_in(text):
    """Add up the damage figures in an effect text, every hit counted.

    Args:
        text: The effect text, or one line of it.

    Returns:
        The total, as a percentage.
    """
    return sum(int(share) * int(before or after or 1) for share, before, after in DAMAGE.findall(text))


def figures(text):
    """Pull the damage, shield and draw figures out of what an effect text does when played.

    Args:
        text: The effect text, as the generated data writes it.

    Returns:
        The `Features` the text states, leaving out its "Retain:" lines.
    """
    text = RETAIN_LINE.sub("", text)
    return Features(
        damage=damage_in(text),
        shield=sum(int(found) for found in SHIELD.findall(text)),
        draw=sum(int(found) for found in DRAW.findall(text)),
        spread=sum(damage_in(line) for line in text.splitlines() if ALL_ENEMIES.search(line)),
    )


def cost(name):
    """Say what a card costs to play.

    Args:
        name: The card name, in any spelling.

    Returns:
        The Action Point cost, `X_COST` when it spends everything left, or `ASSUMED_COST` for a card the data
        does not carry.
    """
    return CARD_COST.get(canonical(name), ASSUMED_COST)


def attribute_of(name):
    """Say which attribute a card attacks with.

    A card has no attribute of its own. It carries whichever the combatant holding it has, which is why this
    goes through the owner rather than reading something off the card.

    Args:
        name: The card name, in any spelling.

    Returns:
        The attribute name, or None when the card has no known owner.
    """
    return COMBATANT_ATTRIBUTE.get(owner(canonical(name)))


def category(name):
    """Say what kind of card this is.

    Args:
        name: The card name, in any spelling.

    Returns:
        The category, or None for a card the data does not carry.
    """
    return CARD_CATEGORY.get(canonical(name))


def description(name):
    """Give a card's effect text as the client writes it.

    Args:
        name: The card name, in any spelling.

    Returns:
        The text, or an empty string for a card the data does not carry.
    """
    return text_of(canonical(name))


def text_of(name):
    """Give a card's effect text, as the version of it the deck holds when the deck has been read.

    Args:
        name: The canonical card name.

    Returns:
        The deck's text, else the base text, or an empty string for a card the data does not carry.
    """
    return DECK.get(name) or DESCRIPTIONS.get(name) or ""


def on_play(name):
    """Give the part of a card's effect text that happens when it is played.

    Args:
        name: The card name, in any spelling.

    Returns:
        The text without its "Retain:" lines.
    """
    return RETAIN_LINE.sub("", description(name))


def settle_deck():
    """Value every card by the version of it `COPIES` holds, the weakest where its copies differ."""
    DECK.clear()
    DECK.update({name: min(texts, key=lambda text: strength(figures(text))) for name, texts in COPIES.items()})
    parsed.cache_clear()


def use_deck(copies):
    """Take a fresh read of the deck in place of everything known about it.

    Args:
        copies: Canonical card name to the effect texts its copies were matched to, from `piles`. A `Counter` of copies per text, or
            any collection of texts, each then counted once.
    """
    COPIES.clear()
    COPIES.update({name: Counter(texts) for name, texts in copies.items()})
    settle_deck()


def change_deck(name, text, by):
    """Add or take away one copy of a card, in one version.

    Args:
        name: The canonical card name.
        text: The version's effect text, from `piles.version_of`.
        by: 1 for a copy gained, -1 for one removed.
    """
    held = COPIES.setdefault(name, Counter())
    held[text] += by
    if held[text] <= 0:
        del held[text]
    if not held:
        del COPIES[name]
    settle_deck()


def worth_clearing(name):
    """Say whether a card dealt to you is better played than held, once nothing better is left to play.

    Args:
        name: The card name, in any spelling.

    Returns:
        True for any Curse with a fixed cost, since a Curse left in hand only clogs it. A Status Ailment counts when it only hurts
        while it sits in hand, or when its text does nothing on play.
    """
    kind, text = category(name), description(name)
    return kind in DEALT_TO_YOU and cost(name) != X_COST and (kind == "CURSE" or bool(HELD_HARM.search(text)) or not INERT_EFFECT.search(text))


def clearing_order(name):
    """Order the cards worth clearing: the ones that deal damage first, then the cheapest.

    Args:
        name: The card name, in any spelling.

    Returns:
        A sort key, smallest first.
    """
    return "damage" not in description(name).lower(), cost(name)


def worth_playing(name):
    """Say whether a card is one the player would ever choose to play.

    Args:
        name: The card name, in any spelling.

    Returns:
        False for a Curse, a Status Ailment or a card that helps by being held, True for anything else, including a card not in the data.
    """
    return category(name) not in DEALT_TO_YOU and not helps_held(name)


def helps_held(name):
    """Say whether a card does its good while it sits in hand, and so is worth keeping rather than playing.

    Args:
        name: The card name, in any spelling.

    Returns:
        True for a card of your own whose text opens with "If in hand".
    """
    return category(name) not in DEALT_TO_YOU and bool(HELD_HELP.match(description(name)))


def value(name, board):
    """Say what a card is worth here, in damage terms, once the kits in play have had their say.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        The generic `rated` figure, adjusted by every kit the hand switches on.
    """
    return kits.worth(canonical(name), board, rated(name, board), lambda other: rated(other, board))


def rated(name, board):
    """Say what a card is worth by its own text alone.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        A single figure combining the damage, shield and draw the card states, with damage raised when the
        card's attribute is the one the enemies are weak to.
    """
    doing = features(name)
    matched = board.weakness is not None and attribute_of(name) == board.weakness
    if wasted(name, board):
        return 0
    hit = doing.damage + doing.spread * (board.enemies - 1)
    worth = strength(doing._replace(damage=0 if board.invulnerable else hit * (WEAKNESS_BONUS if matched else 1)))
    if not worth:
        worth = UNREAD_VALUE * max(cost(name), 1)
    if lit_up(name, board):
        worth += EPIPHANY_BONUS
    return worth


def wasted(name, board):
    """Say whether a card would do nothing, being all damage while an enemy cannot lose Health.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        True for a card with damage and nothing else on an invulnerable turn.
    """
    doing = features(name)
    return board.invulnerable and doing.damage > 0 and not strength(doing._replace(damage=0))


def strength(doing):
    """Say what a card's figures are worth together, in damage terms.

    Args:
        doing: The card's `Features`.

    Returns:
        The damage, plus the shield and draw at their exchange rates.
    """
    return doing.damage + SHIELD_WEIGHT * doing.shield + DRAW_VALUE * doing.draw


def lit_up(name, board):
    """Say whether this is the card the run has lit up for an Epiphany.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        True when the glow read off the screen belongs to this card.
    """
    return board.epiphany is not None and canonical(board.epiphany) == canonical(name)


def phase(name, board):
    """Say when in a turn a card belongs.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        One of the `PHASE_` values, or a kit's place between two of them, lowest being earliest in the turn.
    """
    if canonical(name) in BREAKDOWN_CARDS:
        return PHASE_ESCAPE
    if lit_up(name, board):
        return PHASE_EPIPHANY
    return kits.phase(canonical(name), board, generic_phase(name))


def generic_phase(name):
    """Say when in a turn a card belongs by its cost and text alone.

    Args:
        name: The card name, in any spelling.

    Returns:
        One of the `PHASE_` values from `PHASE_FREE` on.
    """
    price = cost(name)
    if price == X_COST:
        return PHASE_SPENDS_EVERYTHING
    if price == 0:
        return PHASE_FREE
    kind = category(name)
    if kind == SETUP_CATEGORY or features(name).draw:
        return PHASE_SETUP
    if kind not in DEALT_TO_YOU and PRIME.search(on_play(name)):
        return PHASE_PRIME
    if kind == ATTACK_CATEGORY:
        return PHASE_ATTACK
    return PHASE_OTHER


def buying_order(name, board):
    """Build the sort key that decides which cards a turn can afford.

    Value per Action Point, rather than value alone, because the question is what to spend a limited budget
    on. A card with no fixed price sorts last however good it looks, since it takes everything that is left
    and so can only ever be the turn's final play.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        A sort key putting the best buy first.
    """
    price = cost(name)
    return price == X_COST, -value(name, board) / max(price, 1)


def best_buy(ranked, budget, board):
    """Pick the cards with a fixed price that are worth the most together within the turn's Action Points.

    Buying the best value per point first can strand points: a 1-point Basic attack bought ahead of a 3-point attack leaves 2 points and
    nothing to spend them on.

    Args:
        ranked: The playable hand cards with a fixed price, best buy first.
        budget: The Action Points to spend.
        board: The `Board` they would be played into.

    Returns:
        The cards to buy, best buy first. A tie goes to the set spending more points, then to the set of more cards.
    """
    worth = [value(card["name"], board) for card in ranked]
    prices = [cost(card["name"]) for card in ranked]
    best, best_key = (), (0, 0, 0)
    for size in range(1, len(ranked) + 1):
        for picked in combinations(range(len(ranked)), size):
            spent = sum(prices[index] for index in picked)
            key = (sum(worth[index] for index in picked), spent, size)
            if spent <= budget and key > best_key:
                best, best_key = picked, key
    return [ranked[index] for index in best]


def plan(hand, board):
    """Choose the cards to play this turn, in the order to play them.

    Two questions, answered in order, because answering them together gets both wrong. What the budget buys is
    settled on the most value the points can buy, so a cheap card cannot crowd out a dear one that wins the fight. Only then are the survivors put into phase order, and
    cards that tie keep the order the hand had.

    Args:
        hand: Hand cards as `_hand_cards` reads them, each a dict with at least a `name`.
        board: The `Board` this is being decided against.

    Returns:
        The hand cards to play, in order, costing no more than the Action Points available.
    """
    if not board.hand:
        board = board._replace(hand=tuple(canonical(card["name"]) for card in hand))
    playable = (card for card in hand if worth_playing(card["name"]) and not kits.held(canonical(card["name"]), board)
                and not wasted(card["name"], board))
    budget = board.action_points
    ranked = sorted(playable, key=lambda held: buying_order(held["name"], board))
    chosen = best_buy([card for card in ranked if cost(card["name"]) != X_COST], budget, board)
    spenders = [card for card in ranked if cost(card["name"]) == X_COST]
    if spenders and sum(cost(card["name"]) for card in chosen) < budget:
        # It takes the rest of the turn's points, so it is worth playing only while some remain, and nothing can follow it.
        chosen.append(spenders[0])
    return sorted(chosen, key=lambda held: phase(held["name"], board))
