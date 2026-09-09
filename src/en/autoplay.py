"""Work out what the game's own Auto AI played, from a recording of the hands it held.

`src/en/observe.py` writes down one frame at a time while Chaos runs with Auto switched on. It records what
the screen showed and nothing else, so every inference about what Auto actually did lives here and can be
rewritten and re-run against the same recording rather than costing another capture session.

Two views come out of the same frames, because the picker has two jobs to supervise. A decision is one card
Auto chose from one hand, which is what `battle.choose` produces. A turn is the whole set it spent a turn on,
which is what `cards.plan` produces. The turn view is the weaker signal but it survives Auto playing faster
than the bot samples, so it uses frames the decision view has to throw away.

Nothing here treats a hand as a set. Several copies of a card in one hand is ordinary, so a name still being
present says nothing about whether a copy of it was played - only the count does. Names are folded through
`cards.canonical` first, because the reader returns the same card as `NA:Attack Response` one frame and
`NA: Attack Response` the next, and an unfolded diff would read that as one card leaving and another arriving.
"""

from collections import Counter, namedtuple

from src.en.cards import canonical

# One recorded battle frame, as `observe.py` writes it. `hand` holds `(name, key)` pairs in screen order.
Frame = namedtuple("Frame", ["at", "hand", "count", "points", "weakness", "egos", "enemies"],
                   defaults=[0.0, (), 0, True, None, (), 0])
# One card Auto chose from one hand, with the board state it chose in.
Decision = namedtuple("Decision", ["hand", "played", "points", "weakness"])
# Everything Auto spent one turn on. `ambiguous` marks a turn where it outran the sampling rate.
Turn = namedtuple("Turn", ["opening", "played", "ambiguous"])


def names_of(frame):
    """List the hand's card names as the data spells them.

    Args:
        frame: The recorded frame.

    Returns:
        The canonical names, in screen order.
    """
    return [canonical(name) for name, _ in frame.hand]


def departures(before, after):
    """Count which cards left the hand between two frames.

    Args:
        before: The earlier frame.
        after: The later frame.

    Returns:
        A `Counter` of canonical names, counting copies rather than testing presence.
    """
    return Counter(names_of(before)) - Counter(names_of(after))


def dealt_again(before, after):
    """Say whether the hand was dealt again between two frames.

    A growing hand is not enough on its own, because a card that draws grows it too. What separates the two
    is what happened to the cards already held: a fresh deal discards the lot first, while a draw leaves them
    where they were. So the hand has to grow and everything in it has to have gone.

    A deal that redraws a name the old hand held would still look like a draw on that test alone, and with a
    deck holding several copies of a card that is not rare. So the Action Point readout is asked as well:
    points refresh when a turn starts, so a readout going from dark to lit alongside a growing hand is a
    fresh turn even when some names carried over.

    What remains unresolvable is a turn ended early, with points still lit, into a deal that redrew a name.
    Both signals miss that one, and the cost is a turn boundary read as a draw.

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
