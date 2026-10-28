"""The shape every kit takes, and the name a card has before its Epiphany."""

import re
from functools import lru_cache

from src.en.game_battle import CARD_OWNER
from src.en.game_text import DESCRIPTIONS

# A line the generator marks as firing when the card is kept in hand at the end of the turn, captured without its prefix.
RETAIN_LINE = re.compile(r"^Retain: (.*)$", re.M)
# The Epiphany a card has been upgraded with, which the client writes as a suffix: "Shard:Light (Cycle)".
EPIPHANY_SUFFIX = re.compile(r"\s*\([^)]*\)$")
# What follows "Create" in a card's text, which starts with the name of the card it makes: "Create 2 Heart Breaker".
CREATES = re.compile(r"Create (?:\d+ |X )?(.+)")

# Where a card sits in a turn, lowest first. Here rather than in cards.py so a kit can place a card between two of them.
PHASE_ESCAPE = 0
PHASE_EPIPHANY = 1
# Upgrade cards buff the rest of the battle, so even a free card is better played after one.
PHASE_UPGRADE = 2
PHASE_FREE = 3
PHASE_SETUP = 4
PHASE_PRIME = 5
PHASE_ATTACK = 6
PHASE_OTHER = 7
PHASE_SPENDS_EVERYTHING = 8

# The data's categories for attack and skill cards.
ATTACK_CATEGORY = "ATK"
SKILL_CATEGORY = "SKILL"


# Every hook strips the same few names many times a frame.
@lru_cache(maxsize=1024)
def base_name(name):
    """Drop the Epiphany from a card name.

    Args:
        name: A card name, maybe upgraded.

    Returns:
        The name the card has before any Epiphany.
    """
    return EPIPHANY_SUFFIX.sub("", name)


def count(names, group):
    """Count the cards from one group among some cards.

    Args:
        names: Canonical card names, from the hand or from what a turn has played.
        group: Base names of the cards to count.

    Returns:
        How many are in `group`, in any Epiphany.
    """
    return sum(base_name(name) in group for name in names)


def text(name, board):
    """Give the effect text of the version of a card the deck holds.

    Args:
        name: A canonical card name, maybe upgraded.
        board: The `cards.Board`, whose `deck` holds the texts the last deck read matched.

    Returns:
        The deck's text, else the base text, or an empty string for a card the data does not carry.
    """
    card = base_name(name)
    return board.deck.get(card) or DESCRIPTIONS.get(card) or ""


def retain_lines(name, board):
    """List what the version of a card the deck holds does when kept in hand, which an Epiphany can change or drop.

    Args:
        name: A canonical card name, maybe upgraded.
        board: The `cards.Board`, whose `deck` holds the texts the last deck read matched.

    Returns:
        Each "Retain:" line's effect, empty for a card that does nothing kept.
    """
    return RETAIN_LINE.findall(text(name, board))


def owned(combatant):
    """Find the cards a combatant brings to a deck, and the cards those create in battle, which the data gives no owner.

    Args:
        combatant: The combatant's name, as `CARD_OWNER` spells it.

    Returns:
        The base names of every card the data says is theirs, and of every card one of them creates.
    """
    theirs = {base_name(name) for name, owner in CARD_OWNER.items() if owner == combatant}
    made = {made for name in theirs for line in CREATES.findall(DESCRIPTIONS.get(name, "")) for made in DESCRIPTIONS
            if line.startswith(made) and not line[len(made):len(made) + 1].isalnum()}
    return frozenset(theirs | made)


class Kit:
    """One playstyle. Every hook does nothing unless a subclass overrides it, so a kit only says what it changes.

    Hooks get the `cards.Board`, whose `hand` holds canonical names left to right. A kit never imports `cards.py`, which imports this.
    """

    # Who the kit plays, for the log.
    name = ""
    # Base names of the cards that switch the kit on while one is in hand.
    cards = frozenset()
    # Base names of the cards the kit moves in the turn, and the phase each goes to, for the default `phase`.
    places = {}
    # Base names of the Finale cards, which end the turn on play without the end-turn key.
    finales = frozenset()

    def claims(self, name):
        """Say whether a card switches this kit on.

        Args:
            name: A canonical card name from the hand.

        Returns:
            True when the card, without its Epiphany, is one of the kit's.
        """
        return base_name(name) in self.cards

    def reading(self, hand, count):
        """Correct the hand reading where the kit knows a card's place better than OCR does.

        Args:
            hand: Hand cards as `_hand_cards` reads them, with canonical names.
            count: The hand size the hand counter reads.

        Returns:
            The hand, corrected or as it was.
        """
        return hand

    def held(self, name, board):
        """Say whether a card must stay in hand, neither played nor given up to a prompt.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True to keep it.
        """
        return False

    def worth(self, name, board, base, rate):
        """Adjust what a card is worth to the turn.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, for a kit that prices one card against another.

        Returns:
            The value to plan with.
        """
        return base

    def phase(self, name, board, base):
        """Place a card in the turn where the generic order puts it wrong.

        Args:
            name: The card being placed.
            board: The `cards.Board` it would be played into.
            base: Where the generic order puts it.

        Returns:
            A `PHASE_` value or a number between two of them, the card's `places` entry by default, else `base`.
        """
        return self.places.get(base_name(name), base)

    def fodder(self, opener, name, board):
        """Say whether a prompt should give up a card ahead of the rest, even one the kit holds.

        Args:
            opener: The card whose play raised the prompt.
            name: A hand card the prompt could take.
            board: The `cards.Board` of the hand on offer.

        Returns:
            True to give it up first.
        """
        return False

    def waiting(self, names, count):
        """Say whether the turn should sit for a frame rather than play or end.

        Args:
            names: Every card the hand reads as.
            count: The hand size the hand counter reads.

        Returns:
            True while the game is still about to change the hand by itself.
        """
        return False
