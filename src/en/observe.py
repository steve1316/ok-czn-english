"""Write down what the game's own Auto AI does, so the fork's picker can be measured against it.

Sortie has no Auto button, which is why the fork picks cards itself. Chaos has one, and upstream already
switches it on - `handle_battle_auto_check` looks for the button and clicks it when it is off. So Chaos is
the same game, the same cards and the same combatants, played by a reference implementation, on a screen the
bot already reads once a second. Watching it costs one more read of what is already on screen.

What gets written down is only what the screen showed. Which card Auto played, where a turn began, whether a
card was played or discarded - all of that is inference, and it lives in `src/en/autoplay.py` where it can be
rewritten and re-run against the same file. A wrong guess here would cost another capture session.

This changes no behaviour. Upstream's handler runs first and its answer is returned untouched, so Chaos plays
exactly as it did whether the recorder works, fails, or is deleted. A failure inside it is logged once and
swallowed for the same reason: losing data is cheap and losing a run is not.
"""

import json
import time

from ok import Logger

from src.en import board
from src.en.handlers import loaded, register, replace

logger = Logger.get_logger(__name__)

# Where the recording goes. `data/` is already in `.gitignore`, so nothing here can reach a commit, and the
# file is append-only text that can be deleted at any time without breaking anything.
RECORDING = "data/auto_play.jsonl"

_patched = False
_complained = False


def seen(task):
    """Read one battle frame into the record that gets written down.

    Args:
        task: The running task.

    Returns:
        A dict of what the screen showed, ready to serialise.
    """
    utils_sortie = loaded("utils_sortie")
    hand = utils_sortie._hand_cards(task) or [] if utils_sortie else []
    frame = board.frame_of(task)
    return {
        "at": round(time.time(), 3),
        "hand": [[card.get("name"), card.get("key")] for card in hand],
        "count": len(hand),
        "points": board.has_action_points(task),
        "weakness": board.weakness(task),
        "egos": board.affordable_egos(task),
        "enemies": len(board.enemy_counters(frame)),
    }


def write(task):
    """Append one frame's record to the recording.

    Args:
        task: The running task.
    """
    with open(RECORDING, "a", encoding="utf-8") as recording:
        recording.write(json.dumps(seen(task)) + "\n")


def install():
    """Watch Chaos battles without changing what they do.

    Runs once per task load, so it has to be safe to call again: a wrapper already in place is left alone
    rather than wrapped in a second one.
    """
    utils_chaos = loaded("utils_chaos")
    if utils_chaos is None:
        return
    original = getattr(utils_chaos, "handle_battle_auto_check", None)
    if original is None:
        return

    def watching(task):
        """Run upstream's Chaos battle frame, then write down what was on screen.

        Args:
            task: The running task.

        Returns:
            Whatever upstream's own handler returns, untouched.
        """
        on_battle = original(task)
        if on_battle:
            try:
                write(task)
            except Exception as error:
                # Said once. A recorder that cannot write costs data, and saying so every frame would cost
                # the log, so the run carries on either way.
                global _complained
                if not _complained:
                    logger.error(f"could not record the battle frame: {error}", exception=error)
                    _complained = True
        return on_battle

    # A distinct name is what makes installing twice a no-op, the same way `rewards.py` wraps a handler:
    # `replace` matches on `__name__`, so once the list holds this there is nothing named after the original
    # left for a later install to wrap again. The module attribute is deliberately left alone, since the
    # handler lists are what the modes actually run.
    watching.__name__ = f"{original.__name__}_recording"
    if replace("handle_battle_auto_check", watching):
        logger.info(f"recording what Auto plays to {RECORDING}")


def apply():
    """Watch Chaos battles once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
