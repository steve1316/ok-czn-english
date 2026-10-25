"""Keep upstream's Enter handler on the one button that means Enter on the Global client.

Upstream presses any "进入" across the bottom fifth of the screen. The Global client captions its round action button
"Enter", and since the 2026-10-01 update it also prints an "Enter" key hint on Select and Confirm buttons, which
upstream pressed before the screen's own handler had picked anything. On a Sortie event the round button attacks the
object, so it is also left alone while an option is offered. Story mode keeps upstream's handler as it is.
"""

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap
from src.en.screen import in_region

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "the Enter button only"
# What the catalog turns the client's "Enter" into.
ENTER = "进入"
# The round action button. All 72 Enter presses in a month of pre-update logs landed at x 0.937-0.946, y 0.898-0.923,
# and the key hints on other buttons sit left of 0.87 - the Select button's is at 0.844.
BUTTON = (0.90, 0.85, 1.0, 1.0)
# Upstream's event option templates, the band it reads them from and its cutoff, as `recognize_event_options` has them.
# Of 64 captures showing one, only the Sortie rally-signal event also has the button's "Enter" up.
OPTION_TEMPLATES = [f"event{number}" for number in range(1, 9)]
OPTION_BAND = (0.198, 0.840, 0.803, 1.000)
OPTION_THRESHOLD = 0.70
# The mode whose Enter is a wide bar on the chapter panel, centred at (0.817, 0.930) - among the key hints, so no region
# can tell them apart.
STORY_MODE = "StoryMode"

_patched = False


def on_the_button(utils):
    """Build the change that keeps `handle_enter` on the round button, and off it while an event option is up.

    Args:
        utils: Upstream's `utils` module, whose `_clean_match` is how `handle_enter` recognises "进入".

    Returns:
        A factory taking the handler currently installed and returning the one to run in its place.
    """
    def factory(original_handle_enter):
        def handle_enter(task):
            if type(task).__name__ == STORY_MODE:
                return original_handle_enter(task)
            button = next((box for box in task.all_texts
                           if utils._clean_match(box.name, ENTER) and in_region(box, BUTTON, task.width, task.height)), None)
            if button is None:
                return False
            if task.find_one(feature_name=OPTION_TEMPLATES, box=task.box_of_screen(*OPTION_BAND), threshold=OPTION_THRESHOLD):
                task.log_info("an event option is on screen, so Enter is left for the option to be chosen")
                return False
            # Upstream reads nothing else off the screen, so showing it the button alone still lets it press it itself.
            with standing_in(task, all_texts=[button]):
                return original_handle_enter(task)

        return handle_enter

    return factory


def install(utils):
    """Keep `handle_enter` on the round button wherever it is registered.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_enter", on_the_button(utils), TAG)


def apply():
    """Keep `handle_enter` on the round button wherever it is registered."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
