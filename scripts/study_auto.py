"""Report how often the fork's card picker would make the same choice as the game's own Auto AI.

`src/en/observe.py` records Chaos battles while Auto plays them. This reads that recording back and answers
three things, in the order they matter.

First, whether the recording is usable at all: Auto may well play faster than the bot samples, and if most
frame transitions lose two cards at once then there are no per-decision labels to learn from. That is a
finding, not a failure, and the turn-level totals still work.

Second, the baseline: how often `cards.plan` already picks what Auto picked. Every later change to the picker
is judged by whether that number goes up.

Third, the work queue: which disagreements happen most. Each recurring one is a rule or a constant to fix.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# One real card is named in geometric symbols, and the Windows console defaults to a codepage that cannot
# encode them. Without this the report dies partway through printing its own results.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.en import autoplay, cards  # noqa: E402
from src.en.observe import RECORDING  # noqa: E402

# How many of the most common disagreements to print. Long enough to see a pattern, short enough to read.
WORST = 15


def load(path):
    """Read a recording back into frames.

    Args:
        path: The recording's path.

    Returns:
        A list of `Frame`, in the order they were written.

    Raises:
        SystemExit: When the recording does not exist yet.
    """
    if not Path(path).exists():
        raise SystemExit(f"no recording at {path} - run Chaos with the observer installed first")
    frames = []
    with open(path, encoding="utf-8") as recording:
        for line in recording:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            frames.append(autoplay.Frame(at=record.get("at", 0.0),
                                         hand=tuple(tuple(card) for card in record.get("hand", ())),
                                         count=record.get("count", 0), points=record.get("points", True),
                                         weakness=record.get("weakness"), egos=tuple(record.get("egos", ())),
                                         enemies=record.get("enemies", 0)))
    return frames


def our_pick(decision):
    """Say which card the fork's picker would have played in a recorded position.

    Args:
        decision: The `Decision` Auto made.

    Returns:
        The card name the picker would choose, or None when it would end the turn.
    """
    hand = [{"name": name, "key": str(index + 1)} for index, name in enumerate(decision.hand)]
    points = cards.BASE_ACTION_POINTS if decision.points else 0
    chosen = cards.plan(hand, cards.Board(action_points=points, weakness=decision.weakness))
    return chosen[0]["name"] if chosen else None


def report_feasibility(frames):
    """Print whether Auto was sampled fast enough to label single decisions.

    Args:
        frames: The recorded frames.
    """
    sizes = Counter()
    for before, after in zip(frames, frames[1:]):
        if autoplay.dealt_again(before, after):
            continue
        sizes[min(sum(autoplay.departures(before, after).values()), 2)] += 1
    total = sum(sizes.values()) or 1
    print(f"frames {len(frames)}, turns {len(autoplay.turns(frames))}")
    print(f"  nothing left      {sizes[0]:5}  ({100 * sizes[0] / total:.0f}%)  thinking or animating")
    print(f"  one card left     {sizes[1]:5}  ({100 * sizes[1] / total:.0f}%)  a usable label")
    print(f"  two or more left  {sizes[2]:5}  ({100 * sizes[2] / total:.0f}%)  faster than we sample")


def report_agreement(made):
    """Print how often the picker agrees with Auto, and where it does not.

    Args:
        made: The `Decision` list reconstructed from the recording.
    """
    if not made:
        print("\nno single-card decisions to compare against")
        return
    disagreements = Counter()
    agreed = 0
    for decision in made:
        ours = our_pick(decision)
        if ours == decision.played:
            agreed += 1
        else:
            disagreements[(decision.played, ours)] += 1
    print(f"\nagreement {agreed}/{len(made)}  ({100 * agreed / len(made):.1f}%)")
    if disagreements:
        print(f"\nworst disagreements (Auto played -> we would play):")
        for (theirs, ours), count in disagreements.most_common(WORST):
            print(f"  x{count:<4} {theirs!r} -> {ours!r}")


def our_turn(turn):
    """Say which cards the picker would have spent a turn on.

    Args:
        turn: The `Turn` Auto played.

    Returns:
        A `Counter` of the card names the picker would have played.
    """
    hand = [{"name": name, "key": str(index + 1)} for index, name in enumerate(turn.opening)]
    return Counter(card["name"] for card in cards.plan(hand, cards.Board()))


def report_turns(played):
    """Print the turn-level picture, the measure that survives Auto outrunning the sampling rate.

    Args:
        played: The `Turn` list reconstructed from the recording.
    """
    scored = [(turn, autoplay.overlap(our_turn(turn), autoplay.comparable(turn))) for turn in played]
    scored = [(turn, share) for turn, share in scored if share is not None]
    if not scored:
        print("\nno turns Auto spent any cards on")
        return
    clean = [share for turn, share in scored if not turn.ambiguous]
    mean = sum(share for _, share in scored) / len(scored)
    spent = sum(sum(autoplay.comparable(turn).values()) for turn, _ in scored)
    print(f"\nturn-level agreement {100 * mean:.0f}%  over {len(scored)} turns")
    if clean:
        print(f"  on the {len(clean)} sampled cleanly {100 * sum(clean) / len(clean):.0f}%")
    print(f"  cards Auto played from the dealt hand, per turn {spent / len(scored):.1f}")
    missed = Counter()
    for turn, _ in scored:
        for name, count in (autoplay.comparable(turn) - our_turn(turn)).items():
            missed[name] += count
    if missed:
        print("\ncards Auto played that we would have left in hand:")
        for name, count in missed.most_common(WORST):
            print(f"  x{count:<4} {name!r}")


def main():
    """Read the recording and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", default=RECORDING, help="the file observe.py wrote")
    arguments = parser.parse_args()
    frames = load(arguments.recording)
    report_feasibility(frames)
    # The turn view leads. It uses every frame, where a single-card label needs Auto to have been caught
    # between two of them - on a real recording that is 25 usable turns against 14 decisions.
    report_turns(autoplay.turns(frames))
    report_agreement(autoplay.decisions(frames))


if __name__ == "__main__":
    main()
