"""Back out of a reward that would push a combatant's Faint Memory past its limit.

Upstream's `handle_center_confirm` clicks any Confirm in the middle of the screen, so on the "exceed its limit"
warning it accepts the reward and part of the save data is altered. This cancels instead, then skips the reward
screen underneath, which would otherwise pick the same card and raise the warning again.
"""

import time

from src.en.desire import BUTTON_REGION as SKIP_REGION, SKIP
from src.en.handlers import insert_before, register
from src.en.screen import text_in_region

# The warning line, read in English off the Global client: "Selecting the reward will cause Faint Memory to exceed its limit."
WARNING = "exceed its limit"
WARNING_REGION = (0.1, 0.3, 0.9, 0.5)
# The dialog's Cancel button, which OCR reads as 取消 with its centre near (0.347, 0.632).
CANCEL = "取消"
CANCEL_REGION = (0.15, 0.55, 0.5, 0.72)
# How long after a Cancel the Skip on the reward screen underneath is still owed. Past this, a Skip on screen belongs to some other page.
SKIP_WITHIN_SECONDS = 10
# When the last Cancel was clicked, as a `time.monotonic()` reading kept on the task.
STATE = "_en_memory_limit_cancelled"
# The handler this one runs ahead of, so the warning never reaches it.
ANCHOR = "handle_center_confirm"

_patched = False


def handle_memory_limit(task):
    """Cancel the Faint Memory warning, then skip the reward screen it was raised from.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if text_in_region(task, WARNING, WARNING_REGION):
        cancel = text_in_region(task, CANCEL, CANCEL_REGION)
        # Claimed even without a Cancel to click, so the Confirm below this handler never gets the frame.
        if cancel is None:
            task.log_info("Faint Memory limit warning on screen, but no Cancel button was read")
            return True
        task.log_info("Reward would push Faint Memory past its limit, clicking Cancel")
        task.click_box(cancel)
        setattr(task, STATE, time.monotonic())
        task.sleep(1)
        return True

    if time.monotonic() - (getattr(task, STATE, None) or float("-inf")) > SKIP_WITHIN_SECONDS:
        return False
    skip = text_in_region(task, SKIP, SKIP_REGION)
    if skip is None:
        return False
    task.log_info("Skipping the reward that would have pushed Faint Memory past its limit")
    task.click_box(skip)
    setattr(task, STATE, None)
    task.sleep(1)
    return True


def apply():
    """Cancel the Faint Memory warning wherever a mode would otherwise confirm it."""
    global _patched
    if _patched:
        return
    register(lambda: insert_before(ANCHOR, handle_memory_limit))
    _patched = True
