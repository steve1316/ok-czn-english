"""Let a run take the rest area it reaches, even when it was started partway through a floor.

Upstream rests, meditates or buys a Sortie Epiphany only while `node_status["flash_or_rest"]` is set. It sets
the flag on the route selection screen and clears it once one of those is taken, so each rest area is used
once. But every fresh status starts with the flag off, so a run started on anything other than the route
screen walks past its first rest area - a Chaos run started inside the Treasure Trove skipped the rest right after it.

Starting the flag on is safe because resting, meditating and buying an Epiphany each still clear it, so one rest
area is still used at most once. The route screen sets it again before the next one either way.

The route screen is also the only thing that re-arms it, which is the second half of this module. A run that
does not pass through that screen spends the flag on its first rest area and never gets it back: one measured
run went 6.5 minutes and zero route screens, rested once, then skipped three safe zones in a row, each reading
the rest feature at over 96% while the game still offered an interaction. The game prints the count on screen,
so where it says one is going spare, upstream's answer is overridden for the length of that one call.
"""

import re

from ok import Logger

from src.en.handlers import loaded, register, wrap

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "rest from the start"
OFFERED_TAG = "rest on an offered interaction"
# Upstream's flag for "this rest area has not been used yet".
FLAG = "flash_or_rest"
# The count the safe zone prints along its bottom edge, as "Available Safe Zone Interactions: 1". Matched
# loosely because only the number is load bearing, and read as text rather than at a point because the line
# moves with its own length. Shops are exempt from the count, which is why only rest and meditate consult it.
INTERACTIONS = re.compile(r"safe\s*zone\s*interactions\D*(\d+)", re.I)
# The handler each mode gates a safe zone on, by the module that defines it. Chaos rests through `utils`,
# Sortie through its own copy, and Story has neither.
GATED_ON_FLAG = {"utils": "handle_rest", "utils_sortie": "handle_rest_sortie"}

_patched = False


def ready_to_rest(original_initial_node_status):
    """Wrap upstream's status builder so every fresh status allows the next rest area.

    Upstream builds a fresh status here on Start, on entering a run and on clearing a floor, and looks the
    builder up on its own module each time, so wrapping it covers all three.

    Args:
        original_initial_node_status: Upstream's `_initial_node_status`.

    Returns:
        The wrapped builder.
    """
    def initial_node_status():
        status = original_initial_node_status()
        status[FLAG] = True
        return status

    return initial_node_status


def interactions_left(task):
    """Read how many safe zone interactions the game says are still going spare.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        The count, or None when the line is not on screen - which is any non-safe-zone screen, and a
        Chinese client, where upstream's own flag stays in charge.
    """
    for box in getattr(task, "all_texts", None) or []:
        found = INTERACTIONS.search(box.name)
        if found:
            return int(found.group(1))
    return None


def taking_the_offered_interaction(original):
    """Wrap a safe zone handler so an interaction the game is offering is one upstream will spend.

    Args:
        original: The upstream handler, which reads `FLAG` to decide whether the area is still unused.

    Returns:
        The wrapped handler.
    """
    def handler(task):
        status = getattr(task, "node_status", None)
        # A stale off is the only thing worth overriding. With the flag already on upstream needs no help,
        # which also keeps the screen read off every frame but the ones that were going to skip the area.
        if status is None or status.get(FLAG, False) or not interactions_left(task):
            return original(task)
        status[FLAG] = True
        try:
            return original(task)
        finally:
            # Put back the off this found, so the override lasts one call and never the run. Upstream clears
            # the flag itself when it spends the area, which lands on the same answer.
            if status.get(FLAG, False):
                status[FLAG] = False

    return handler


def install(utils):
    """Start every fresh run status ready to rest, and take an interaction the game is still offering.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "_initial_node_status", ready_to_rest, TAG)
    # `wrap` reads the handler off the module, so a mode that has not been imported yet simply misses and is
    # picked up on the load that imports it.
    for module_name, handler_name in GATED_ON_FLAG.items():
        wrap(loaded(module_name), handler_name, taking_the_offered_interaction, OFFERED_TAG)


def apply():
    """Start every fresh run status ready to rest, and take an interaction the game is still offering."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
