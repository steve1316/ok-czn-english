"""Let a run take the rest area it reaches, even when it was started partway through a floor.

Upstream rests, meditates or buys a Sortie Epiphany only while `node_status["flash_or_rest"]` is set. It sets
the flag on the route selection screen and clears it once one of those is taken, so each rest area is used
once. But every fresh status starts with the flag off, so a run started on anything other than the route
screen walks past its first rest area - a Chaos run started inside the Treasure Trove skipped the rest right after it.

Starting the flag on is safe because resting, meditating and buying an Epiphany each still clear it, so one rest
area is still used at most once. The route screen sets it again before the next one either way.
"""

from ok import Logger

from src.en.handlers import loaded, register, wrap

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "rest from the start"
# Upstream's flag for "this rest area has not been used yet".
FLAG = "flash_or_rest"

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


def install(utils):
    """Start every fresh run status ready to rest.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "_initial_node_status", ready_to_rest, TAG)


def apply():
    """Start every fresh run status ready to rest."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
