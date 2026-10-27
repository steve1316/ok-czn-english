"""Leave the end-of-run summary by its Confirm button, and close the deck view if a stray tap opened it.

The summary lists the run's deck before its Confirm button has drawn, and upstream's `handle_event_task` reads one of those cards as an
event option and taps it. That opens the Cards Owned view, which nothing closes until `handle_stuck_log` gives up 10 seconds later.
"""

from src.en.handlers import insert_before, register
from src.en.screen import text_in_region

# Read in English off the Global client: a line only the summary prints, and the deck view's title.
SUMMARY = "Completion Time"
DECK_VIEW = "Cards Owned"
WHOLE_SCREEN = (0.0, 0.0, 1.0, 1.0)
TITLE_REGION = (0.3, 0.0, 0.7, 0.12)
# Where the deck view draws its X, the same box `handle_stuck_log` searches for it.
CLOSE_REGION = (0.921, 0.003, 0.998, 0.100)
# How long a summary frame waits for its Confirm button, which `handle_confirm` ahead of this then presses.
WAIT_SECONDS = 0.5
# The handler these run ahead of, so it never sees the summary's cards.
ANCHOR = "handle_event_task"

_patched = False


def handle_run_summary(task):
    """Close the deck view, or hold the summary until its Confirm button draws.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if text_in_region(task, DECK_VIEW, TITLE_REGION):
        close = task.find_one(feature_name="close_page", box=task.box_of_screen(*CLOSE_REGION))
        if close is None:
            return False
        task.log_info("Cards Owned view is open, closing it")
        task.click_box(close)
        task.sleep(1)
        return True
    if not text_in_region(task, SUMMARY, WHOLE_SCREEN):
        return False
    task.log_info("run summary on screen, waiting for its Confirm button")
    task.sleep(WAIT_SECONDS)
    return True


def apply():
    """Run the summary handler ahead of the event handler in every mode that has one."""
    global _patched
    if _patched:
        return
    register(lambda: insert_before(ANCHOR, handle_run_summary))
    _patched = True
