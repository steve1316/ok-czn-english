"""Work out what the game's own Auto AI played, from a recording of the hands it held.

`src/en/observe.py` writes down one frame at a time while Chaos runs with Auto switched on. It records what
the screen showed and nothing else, so every inference about what Auto actually did lives here and can be
rewritten and re-run against the same recording rather than costing another capture session.
"""

from bisect import bisect_left, bisect_right
from collections import Counter, namedtuple
from difflib import SequenceMatcher
from functools import reduce
from operator import or_

from src.en.cards import CARD_COST, canonical, is_card_name
from src.en.quality import fold

# One recorded battle frame, as `observe.py` writes it. `hand` holds `(name, key)` pairs in screen order.
Frame = namedtuple("Frame", ["at", "hand", "count", "points", "weakness", "egos", "enemies"],
                   defaults=[0.0, (), 0, True, None, (), 0])
# One card Auto chose from one hand, with the board state it chose in.
Decision = namedtuple("Decision", ["hand", "played", "points", "weakness"])
# Everything Auto spent one turn on. `ambiguous` marks a turn where it outran the sampling rate.
Turn = namedtuple("Turn", ["opening", "played", "ambiguous"])

# How alike two readings must be for one to be the other read again - "Joker" and "Jokel" score 0.8, a played card and the
# unrelated card drawn after it rarely clear 0.5. A reading cut short is caught apart from this, by being part of the other.
SAME_READING = 0.75
# The shortest piece of a name worth matching inside another, so a stray glyph is not taken for every card holding it.
SHORTEST_PIECE = 3
# Seconds from a burst grab within which a full frame's hand is dropped. The full frame and the band are read by separate
# OCR passes, which disagree on a card often enough that interleaving them fakes plays.
COVERED = 1.0
# The longest gap between two grabs that can still show one settled hand. Grabs come every ~0.13s.
STEADY = 0.5
# Seconds either side of a grab to look for a card it missed. On a live battle the reader lost Chain Fire for 0.6s and got it
# back, and no window wider than this removed any more fake plays.
FLICKER = 1.5


# Nothing here treats a hand as a set. Several copies of a card in one hand is ordinary, so a name still being
# present says nothing about whether a copy was played - only the count does. Names are folded through
# `cards.canonical` first, because the reader returns the same card as `NA:Attack Response` one frame and
# `NA: Attack Response` the next, and an unfolded diff would read that as one card leaving and another arriving.
def names_of(frame):
    """List the hand's card names as the data spells them.

    Args:
        frame: The recorded frame.

    Returns:
        The canonical names, in screen order. A label the reader passed off as a card is left out, by today's label test rather
        than the one the recording was made under.
    """
    return [canonical(name) for name, _ in frame.hand if is_card_name(name)]


def departures(before, after):
    """Count which cards left the hand between two frames.

    Args:
        before: The earlier frame.
        after: The later frame.

    Returns:
        A `Counter` of canonical names, counting copies rather than testing presence. A card that only re-read under
        another name - "Illusion of Golden Daffodils" one frame, "lusion of Golden Daffodils" the next - did not leave.
    """
    held, holding = Counter(names_of(before)), Counter(names_of(after))
    left, arrived = held - holding, holding - held
    for name in list(left.elements()):
        again = next((new for new in arrived if arrived[new] and reads_like(name, new)), None)
        if again:
            left[name] -= 1
            arrived[again] -= 1
    return +left


def reads_like(one, other):
    """Say whether two readings off the hand are likely the same card, read twice.

    Args:
        one: A name from one frame.
        other: A name from the next.

    Returns:
        True when one is part of the other, or the two are only a letter or two apart. Two names the data both knows are
        two cards, since `Ambush` sits inside `Ambush Cover` and a misreading resolves to neither.
    """
    if one in CARD_COST and other in CARD_COST:
        return False
    shorter, longer = sorted((fold(one), fold(other)), key=len)
    if len(shorter) >= SHORTEST_PIECE and shorter in longer:
        return True
    return SequenceMatcher(None, shorter, longer).ratio() >= SAME_READING


def settled(grabs):
    """Keep the burst grabs that caught a hand at rest.

    A grab taken mid-animation reads a card sliding out as gone and back again, which counts as two plays. A grab that
    could not read the counter was covered by a tooltip, and one that read no cards over a non-zero counter caught a play.
    The band reader also drops a card for a second at a time, so a card the grabs either side still read is put back.

    Args:
        grabs: Frames read back from the burst grabs, in time order.

    Returns:
        Each readable grab whose next grab, taken soon after, read the same hand, with any card it missed added under an
        empty key.
    """
    readable = [(grab, Counter(names_of(grab))) for grab in grabs if grab.count is not None]
    readable = [(grab, held) for grab, held in readable if held or not grab.count]
    steady = [(one, held) for (one, held), (other, read) in zip(readable, readable[1:]) if other.at - one.at < STEADY and held == read]
    times = [grab.at for grab, _ in steady]
    kept = []
    for index, (grab, held) in enumerate(steady):
        before = reduce(or_, (counts for _, counts in steady[bisect_left(times, grab.at - FLICKER):index]), Counter())
        after = reduce(or_, (counts for _, counts in steady[index + 1:bisect_right(times, grab.at + FLICKER)]), Counter())
        kept.append(grab._replace(hand=grab.hand + tuple((name, "") for name in ((before & after) - held).elements())))
    return kept


def covered(times, at):
    """Say whether a burst grab was taken close to a moment.

    Args:
        times: Every grab's time, sorted.
        at: The full frame's time.

    Returns:
        True when a grab sits within `COVERED` seconds either side.
    """
    after = bisect_left(times, at)
    return any(abs(times[index] - at) <= COVERED for index in (after - 1, after) if 0 <= index < len(times))


def merged(frames, grabs):
    """Slot the burst grabs in among the full frames, by time.

    Where grabs were running they own the hand, and a full frame there only updates the board. A grab borrows the board
    of the full frame before it, since it read nothing else. At a tie the full frame goes first.

    Args:
        frames: The full recorded frames.
        grabs: Frames read back from the burst grabs, where only `at`, `hand` and `count` mean anything.

    Returns:
        Every frame kept, in time order.
    """
    grabs = sorted(grabs, key=lambda grab: grab.at)
    times = [grab.at for grab in grabs]
    every, board = [], Frame()
    for frame, grabbed in sorted([(frame, False) for frame in frames] + [(grab, True) for grab in settled(grabs)], key=lambda pair: pair[0].at):
        if grabbed:
            frame = board._replace(at=frame.at, hand=frame.hand, count=frame.count)
        else:
            board = frame
            if covered(times, frame.at):
                continue
        every.append(frame)
    return every


def dealt_again(before, after):
    """Say whether the hand was dealt again between two frames.

    A growing hand is not enough, because a card that draws grows it too - what separates them is that a fresh
    deal discards the lot first. A deal redrawing a name the old hand held would still look like a draw, so the
    Action Point readout is asked as well. A turn ended early into such a deal misses both signals.

    Args:
        before: The earlier frame.
        after: The later frame.

    Returns:
        True when a fresh hand was dealt.
    """
    if len(after.hand) <= len(before.hand):
        return False
    if not before.points and after.points:
        return True
    return sum(departures(before, after).values()) == len(before.hand)


def decisions(frames):
    """Pick out the frame transitions where exactly one card left.

    Anything else is unusable as a label. Nothing leaving means Auto was thinking or an animation was
    running. Two or more leaving means it played faster than the bot samples, so which went first is gone.

    Args:
        frames: The recorded frames, in order.

    Returns:
        A list of `Decision`, one per clean transition.
    """
    found = []
    for before, after in zip(frames, frames[1:]):
        if dealt_again(before, after):
            continue
        left = departures(before, after)
        if sum(left.values()) != 1:
            continue
        played = next(iter(left))
        found.append(Decision(hand=tuple(names_of(before)), played=played,
                              points=before.points, weakness=before.weakness))
    return found


def overlap(ours, theirs):
    """Say how much of what Auto spent a turn on we would have played too.

    Counted in copies rather than names, because a hand holding three of a card and a turn spending two of
    them are different facts. Scored against Auto's set rather than ours, so a turn we would have spent more
    cards on is not punished for it - the question is how much of Auto's play we reproduce.

    Args:
        ours: A `Counter` of what the picker would have played.
        theirs: A `Counter` of what Auto actually played.

    Returns:
        The share of Auto's cards we would also have played, 0 to 1, or None when Auto played nothing and
        there is no question to answer.
    """
    spent = sum(theirs.values())
    if not spent:
        return None
    return sum((ours & theirs).values()) / spent


def comparable(turn):
    """Narrow what Auto played to the cards the picker could also have seen.

    A turn deals a hand and then plays on into whatever it draws. The picker is only ever asked about the
    hand in front of it, so counting a card drawn later in the turn as one it failed to play measures how
    fast the bot samples rather than how well it chooses.

    Args:
        turn: The `Turn` Auto played.

    Returns:
        A `Counter` of the cards Auto played that were in the hand it opened the turn with.
    """
    return turn.played & Counter(turn.opening)


def turns(frames):
    """Group the frames into turns and total what left the hand in each.

    Order within a turn is not recovered, which is what lets this count transitions the decision view has to
    discard. The transition into a fresh hand is skipped, since the discard that clears the old one would
    otherwise look like Auto playing everything it held.

    Args:
        frames: The recorded frames, in order.

    Returns:
        A list of `Turn`, one per hand dealt.
    """
    if not frames:
        return []
    found = []
    opening = frames[0]
    played = Counter()
    ambiguous = False
    for before, after in zip(frames, frames[1:]):
        if dealt_again(before, after):
            found.append(Turn(opening=tuple(names_of(opening)), played=played, ambiguous=ambiguous))
            opening, played, ambiguous = after, Counter(), False
            continue
        left = departures(before, after)
        played += left
        ambiguous = ambiguous or sum(left.values()) > 1
    found.append(Turn(opening=tuple(names_of(opening)), played=played, ambiguous=ambiguous))
    return found
