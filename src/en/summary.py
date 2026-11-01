"""Leave the end-of-run screens by their own buttons, and close the detail view a stray tap opened on one.

The summary and the Save Data screens draw their cards before their Confirm or Next button, and upstream's `handle_event_task` reads a
card as an event option and taps it. On the summary that opens Cards Owned until `handle_stuck_log` gives up. On Save Data it opens a
save's details, whose "Can Apply Mutation" reads as an option too and is tapped forever, since upstream closes them below the event handler.
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
# The Save Data screens: the deck flying in, then the saves, whose title `ocr.po` rewrites to upstream's literal.
SAVE_DATA_SCREENS = ("Saving battle data", "存储数据收集完成")
# A save's details, titled in English at its top left, and the X upstream's `handle_stage_end_data_details` taps to close it.
SAVE_DETAILS = "Save Data"
SAVE_DETAILS_REGION = (0.111, 0.103, 0.338, 0.243)
SAVE_DETAILS_CLOSE = (0.883, 0.156)
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


def handle_save_data(task):
    """Close a save's details, or hold the Save Data screens until `handle_next_step` ahead of this has its Next.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if text_in_region(task, SAVE_DETAILS, SAVE_DETAILS_REGION):
        task.log_info("Save Data details are open, closing them")
        task.click(*SAVE_DETAILS_CLOSE)
        task.sleep(1)
        return True
    if not any(text_in_region(task, screen, WHOLE_SCREEN) for screen in SAVE_DATA_SCREENS):
        return False
    task.log_info("Save Data on screen, waiting for its Next button")
    task.sleep(WAIT_SECONDS)
    return True


def apply():
    """Run the end-of-run handlers ahead of the event handler in every mode that has one."""
    global _patched
    if _patched:
        return
    register(lambda: insert_before(ANCHOR, handle_run_summary))
    register(lambda: insert_before(ANCHOR, handle_save_data))
    _patched = True
