"""Rossweisse: hold the two Shards at the ends of her hand and clear everything between, so they fuse into Flicker Blade.

Each turn she starts with Shard:Light on the far left and Shard:Dark on the far right. They fire while held, and once they are the only
cards left they fuse into a free Flicker Blade. The generic picker buys a Shard for its 80% hit and ends the turn while the fusion plays out.
"""

import re

from src.en.game_battle import CARD_COST
from src.en.kits.kit import Kit, base_name
from src.en.quality import fold

# Her two end cards, left then right.
SHARDS = ("Shard:Light", "Shard:Dark")
# What they fuse into. An upgraded pair keeps its Epiphany, so Shard:Light (Cycle) fuses into Flicker Blade (Cycle).
FUSED = "Flicker Blade"
# How a Shard still reads once OCR mangles it - "Sharc", "nard:Dark", "Shard:l" - matched on folded text. No other card's name matches.
READS_AS_SHARD = re.compile(r"shar|ard(?:light|dark)")
# What each Shard trigger makes. Unplayable, and it stays in hand beside the Shards until they fuse.
TASSEL = "Sword Tassel"


def is_shard(name):
    """Say whether a reading is one of the Shards, in any Epiphany.

    Args:
        name: A card name from the hand, canonical or as OCR left it.

    Returns:
        True for a Shard.
    """
    return bool(READS_AS_SHARD.search(fold(name)))


def is_waiting_card(name):
    """Say whether a card just sits in hand until the fusion, so it does not count as the middle.

    Args:
        name: A card name from the hand, canonical or as OCR left it.

    Returns:
        True for a Shard or a Sword Tassel.
    """
    return is_shard(name) or base_name(name) == TASSEL


def fused(shards):
    """Name the Flicker Blade a pair of Shards will fuse into.

    Args:
        shards: The Shard names in hand.

    Returns:
        The Flicker Blade with the Shards' Epiphany, or the plain one when the data has no such variant.
    """
    for shard in shards:
        upgraded = FUSED + shard[len(base_name(shard)):]
        if upgraded in CARD_COST:
            return upgraded
    return FUSED


class Rossweisse(Kit):
    """Keeps the Shards and their Tassels, prices every card between them as a step toward the fusion, and waits the fusion out."""

    name = "Rossweisse"
    cards = frozenset((*SHARDS, TASSEL))

    def claims(self, name):
        """Switch on for a Shard in hand, however OCR read it, or a Sword Tassel, so a hand of Tassels is not played.

        Args:
            name: A card name from the hand.

        Returns:
            True for a Shard or a Tassel.
        """
        return is_waiting_card(name)

    def reading(self, hand, count):
        """Take an end card OCR could not name, or did not read at all, to be a Shard when the Shard at the other end did read.

        Args:
            hand: Hand cards as `_hand_cards` reads them, with canonical names.
            count: The hand size the hand counter reads.

        Returns:
            The hand, with an unreadable or missing end card named as the Shard that sits there.
        """
        if not count or count < len(SHARDS):
            return hand
        shards = [card.get("key") for card in hand if is_shard(card["name"])]
        # Each end key, the Shard that sits on it, and the key the other Shard reads on.
        ends = {"1": (SHARDS[0], str(count)), str(count): (SHARDS[1], "1")}
        read = []
        for card in hand:
            shard, other = ends.get(card.get("key"), (None, None))
            if shard and shards == [other] and card["name"] not in CARD_COST:
                card = {**card, "name": shard}
            read.append(card)
        keys = {card.get("key") for card in read}
        for end, (shard, other) in ends.items():
            # OCR missed the other end outright. It still holds a Shard, so a key pressed blind for an unread card never lands on it.
            if shards == [other] and end not in keys:
                read.insert(0 if end == "1" else len(read), {"name": shard, "key": end})
        return read

    def held(self, name, board):
        """Keep every Sword Tassel, and a Shard while anything but Shards and Tassels is still in hand, read or not.

        Args:
            name: The card in question.
            board: The `cards.Board` it would be played into.

        Returns:
            True for a Tassel, or a Shard with middle cards beside it.
        """
        if base_name(name) == TASSEL:
            return True
        # Live, a hand of 6 read as Shard:Light alone, and the Shard was played with four cards still between.
        return is_shard(name) and (board.hand_size > len(board.hand) or not all(map(is_waiting_card, board.hand)))

    def worth(self, name, board, base, rate):
        """Price each card between the Shards as a step toward the fusion.

        Args:
            name: The card being valued.
            board: The `cards.Board` it would be played into.
            base: What the generic picker made of it.
            rate: Gives the generic value of any card by name, here Flicker Blade's.

        Returns:
            The value to plan with.
        """
        shards = [other for other in board.hand if is_shard(other)]
        if len(shards) < len(SHARDS) or is_shard(name):
            return base
        # Each card cleared from the middle brings the free Flicker Blade a step closer, so it is worth that on top of itself.
        # A flat bonus also tilts value per point toward the cheap cards that clear the middle fastest, which is how Auto plays her.
        return base + rate(fused(shards))

    def waiting(self, names, count):
        """Wait while the two Shards and their Tassels alone are in hand, which reads for 1-2s before they fuse.

        Args:
            names: Every card the hand reads as.
            count: The hand size the hand counter reads.

        Returns:
            True while the fusion is still to come.
        """
        return count <= len(names) and sum(map(is_shard, names)) == len(SHARDS) and all(map(is_waiting_card, names))


KIT = Rossweisse()
