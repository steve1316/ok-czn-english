"""Decide which cards to play in a Sortie battle, and in what order.

Sortie has no Auto button, so the bot picks every card itself. Upstream picks by looking each hand card up in
a list of names the user typed, and plays the first one that matches. On the Global client that list starts
empty, because upstream's default is Chinese card names that English OCR can never match, so in practice
every turn falls through to pressing each hotkey in turn and hoping. This module is what replaces the hoping.

A turn is decided in two steps, because "which cards can I afford" and "what order do they go in" are
different questions and answering them together gets both wrong. First the Action Points are spent on value
per point, so 220% damage for two points is bought ahead of 100% for one, and a cheap card that does little
cannot crowd out a dear one that wins the fight. Then whatever was bought is put in order by phase: a card
the run has lit up for an Epiphany first, then anything free, then setup that makes the rest of the turn
better, then damage, and last a card with no fixed price, since it takes whatever is left.

Nothing here touches the framework. It takes a hand as `_hand_cards` already reads one, plus what is known
about the moment it is being played in, and returns the cards to play. That keeps the judgement testable
without a game running, which matters because the judgement is the whole point.

Every fact it reasons from is the client's own, out of `game_battle.py` and `game_text.py`, so none of it is
guesswork about what a card does. What the reader hands over is not the client's spelling, though, so every
name is folded through `quality` first, the same way the reward code already matches a name off a screen.
"""

import re
from collections import namedtuple
from functools import lru_cache

from src.en.game_battle import CARD_CATEGORY, CARD_COST, CARD_OWNER, COMBATANT_ATTRIBUTE, X_COST
from src.en.game_text import DESCRIPTIONS
from src.en.quality import fold, index

# Action Points a turn starts with, before anything in a run changes the figure.
BASE_ACTION_POINTS = 3
# `X_COST` comes from the generated data rather than being restated here, so a card that spends everything
# left cannot come to mean one thing to the generator and another to this.
# Categories the game deals you rather than ones you choose. A Curse is someone else's doing and a Status
# Ailment is damage waiting to happen, so neither is ever part of a plan.
DEALT_TO_YOU = frozenset({"ABNORM", "CURSE"})
# A card that only makes other cards better, so it wants to land before them.
SETUP_CATEGORY = "POWER"
ATTACK_CATEGORY = "ATK"
# What a card the data has never heard of is assumed to cost. One is both the commonest price and the
# forgiving guess: too low only risks a card that will not play, while too high would refuse it outright.
ASSUMED_COST = 1

# Where a card sits in a turn, lowest first.
PHASE_EPIPHANY = 0
PHASE_FREE = 1
PHASE_SETUP = 2
PHASE_ATTACK = 3
PHASE_OTHER = 4
PHASE_SPENDS_EVERYTHING = 5

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
# counting it would rate a card that does nothing by itself as though it hit hard.
DAMAGE = re.compile(r"(\d+)%[^\n]{0,24}?Damage(?!\s+Amount)")
SHIELD = re.compile(r"(\d+)%[^\n]{0,20}?Shield")
DRAW = re.compile(r"\bDraw (\d+)")

# What a card does, in the terms the ordering cares about.
Features = namedtuple("Features", ["damage", "shield", "draw"])
# What the picker knows about the moment it is choosing in. `weakness` is the attribute the enemies are weak
# to and `epiphany` the hand card the run has lit up. Nothing reads either off a screen yet - both regions
# need pinning down against a frame with a hand in it first - so today they arrive as None and the scoring
# that uses them waits for a reader. The planner is built to take them the day one exists.
Board = namedtuple("Board", ["action_points", "weakness", "epiphany"],
                   defaults=[BASE_ACTION_POINTS, None, None])

# How many distinct readings to remember the folding of. OCR invents new misspellings all session, so this
# is bounded rather than unlimited, and it is far larger than the ten names one frame ever asks about.
CACHED_READINGS = 1024
# Folded card name to the client's own spelling, so a reading run together or in the wrong case still lands.
CARD_INDEX = index(CARD_COST)


@lru_cache(maxsize=CACHED_READINGS)
def canonical(name):
    """Turn a name as read off the screen into the one the data is keyed by.

    Args:
        name: The card name the reader produced.

    Returns:
        The client's spelling, or the name unchanged when nothing matches it.
    """
    return CARD_INDEX.get(fold(name), name)


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
    text = DESCRIPTIONS.get(name) or ""
    return Features(
        damage=sum(int(found) for found in DAMAGE.findall(text)),
        shield=sum(int(found) for found in SHIELD.findall(text)),
        draw=sum(int(found) for found in DRAW.findall(text)),
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
    return COMBATANT_ATTRIBUTE.get(CARD_OWNER.get(canonical(name)))


def category(name):
    """Say what kind of card this is.

    Args:
        name: The card name, in any spelling.

    Returns:
        The category, or None for a card the data does not carry.
    """
    return CARD_CATEGORY.get(canonical(name))


def worth_playing(name):
    """Say whether a card is one the player would ever choose to play.

    Args:
        name: The card name, in any spelling.

    Returns:
        False for a Curse or a Status Ailment, True for anything else, including a card not in the data.
    """
    return category(name) not in DEALT_TO_YOU


def value(name, board):
    """Say what a card is worth here, in damage terms.

    Args:
        name: The card name, in any spelling.
        board: The `Board` it would be played into.

    Returns:
        A single figure combining the damage, shield and draw the card states, with damage raised when the
        card's attribute is the one the enemies are weak to.
    """
    doing = features(name)
    matched = board.weakness is not None and attribute_of(name) == board.weakness
    damage = doing.damage * (WEAKNESS_BONUS if matched else 1)
    worth = damage + SHIELD_WEIGHT * doing.shield + DRAW_VALUE * doing.draw
    if not worth:
        worth = UNREAD_VALUE * max(cost(name), 1)
    if lit_up(name, board):
        worth += EPIPHANY_BONUS
    return worth


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
        One of the `PHASE_` values, lowest being earliest in the turn.
    """
    if lit_up(name, board):
        return PHASE_EPIPHANY
    price = cost(name)
    if price == X_COST:
        return PHASE_SPENDS_EVERYTHING
    if price == 0:
        return PHASE_FREE
    kind = category(name)
    if kind == SETUP_CATEGORY or features(name).draw:
        return PHASE_SETUP
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


def plan(hand, board):
    """Choose the cards to play this turn, in the order to play them.

    Two separate questions, answered in order. Which cards the budget buys is settled on value per Action
    Point, so a cheap card that does little cannot crowd out a dear one that wins the fight. Only then are
    the survivors put into the order they are played in, which is what the phases are for.

    Cards that tie keep the order the hand had, so a turn the picker has no opinion about still plays left to
    right rather than differently on every frame.

    Args:
        hand: Hand cards as `_hand_cards` reads them, each a dict with at least a `name`.
        board: The `Board` this is being decided against.

    Returns:
        The hand cards to play, in order, costing no more than the Action Points available.
    """
    playable = (card for card in hand if worth_playing(card["name"]))
    budget = board.action_points
    chosen = []
    for card in sorted(playable, key=lambda held: buying_order(held["name"], board)):
        price = cost(card["name"])
        if price == X_COST:
            # It takes the rest of the turn's points, so it is worth playing only while some remain, and
            # nothing can follow it.
            if budget > 0:
                chosen.append(card)
                budget = 0
            continue
        if price > budget:
            continue
        budget -= price
        chosen.append(card)
    return sorted(chosen, key=lambda held: phase(held["name"], board))
