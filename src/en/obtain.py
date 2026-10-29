"""Claim each reward on an Obtain screen without the two seconds upstream waits after every tap.

Upstream's `handle_obtain_reward` taps Obtain once per reward, then waits out `click_box`'s one-second `after_sleep` and
another second of its own, so a screen of four rewards spends eight seconds idle. A tap the game drops just leaves Obtain
on the next frame to be tapped again.
"""

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "quick Obtain"
# The longest each of the handler's two waits may run, in seconds. A tap that lands as a Latent Epiphany's card page
# opens hits that page's Select button, which does nothing until a card is chosen.
SETTLE = 0.25

_patched = False


def quick(original):
    """Wrap upstream's Obtain handler so each of its waits is cut to `SETTLE`.

    Args:
        original: Upstream's `handle_obtain_reward`, or another patch's wrapper of it.

    Returns:
        The wrapped handler.
    """
    def handler(task):
        sleep = task.sleep
        # `click_box` waits through `task.sleep` too, so this one stand-in shortens both.
        with standing_in(task, sleep=lambda seconds: sleep(min(seconds, SETTLE))):
            return original(task)

    return handler


def apply():
    """Cut the wait after every Obtain tap in Chaos and Sortie."""
    global _patched
    if _patched:
        return
    register(lambda: wrap(loaded("utils"), "handle_obtain_reward", quick, TAG))
    _patched = True
