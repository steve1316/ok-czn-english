"""Count each combatant's card plays across debug runs, so a kit test run can draft whoever has been played least.

Upstream drafts at random, so the same few combatants kept coming back while others never had their kit run live. The tally lives in
`data/`, which is gitignored, so each machine keeps its own.
"""

import collections
import json
import os

from ok import Logger

from src.en import cards

logger = Logger.get_logger(__name__)

FILE = os.path.join("data", "kit_plays.json")

# Combatant name -> card plays, read from `FILE` on first use.
_plays = None
_complained = False


def debug_run():
    """Say whether this is a `main_debug.py` run, the only kind that drafts for coverage."""
    from ok import og

    return bool((og.config or {}).get("debug"))


def plays():
    """Read how many cards each combatant has played across debug runs.

    Returns:
        A `Counter` of combatant name to plays, or None off a debug run.
    """
    global _plays
    if not debug_run():
        return None
    if _plays is None:
        try:
            with open(FILE, encoding="utf-8") as file:
                _plays = collections.Counter(json.load(file))
        except FileNotFoundError:
            _plays = collections.Counter()
        except (OSError, ValueError) as error:
            logger.error(f"could not read {FILE}, counting from zero: {error}")
            _plays = collections.Counter()
    return _plays


def played(name):
    """Count one card play toward the combatant who owns the card, on a debug run.

    Args:
        name: The canonical name of the card being played, from the battle's plan.
    """
    global _complained
    counts = plays()
    owner = cards.owner(name)
    if counts is None or not owner:
        return
    counts[owner] += 1
    try:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        with open(FILE, "w", encoding="utf-8") as file:
            json.dump(dict(sorted(counts.items())), file, indent=1)
    except OSError as error:
        if not _complained:
            logger.error(f"could not write {FILE}, later failures stay quiet: {error}")
            _complained = True
