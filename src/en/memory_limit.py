"""Answer the two Faint Memory dialogs: back out of one past the limit, and accept a Divine Epiphany's cost.

Upstream's `handle_center_confirm` clicks any Confirm in the middle of the screen, so on the "exceed its limit"
warning it accepts the reward and part of the save data is altered. This cancels instead, then backs out of the
screen underneath - Skip on a reward, Cancel on the shop's removal - which would otherwise pick again and loop.
On a Divine Epiphany's notice the same press lands before the notice has opened, and the card is never taken.
"""

import time

from src.en.desire import BUTTON_REGION, SKIP
from src.en.handlers import insert_before, register
from src.en.screen import centre_of, text_in_region

# The warning line, read in English off the Global client: "Selecting the reward will cause Faint Memory to exceed its limit."
WARNING = "exceed its limit"
WARNING_REGION = (0.1, 0.3, 0.9, 0.5)
# The dialog's Cancel button, which OCR reads as 取消 with its centre near (0.347, 0.632).
CANCEL = "取消"
CANCEL_REGION = (0.15, 0.55, 0.5, 0.72)
# How long after a Cancel the back-out on the screen underneath is still owed. Past this, a button on screen belongs to some other page.
BACK_OUT_WITHIN_SECONDS = 10
# When the last Cancel was clicked, as a `time.monotonic()` reading kept on the task.
STATE = "_en_memory_limit_cancelled"
# The Divine Epiphany notice, read in English off the Global client under "Faint Memory increases by 20 points."
DIVINE = "Would you like to select this card"
# The notice's Confirm button, which OCR reads as 确认 with its centre near (0.666, 0.690).
CONFIRM = "确认"
CONFIRM_REGION = (0.5, 0.6, 0.85, 0.78)
# How long the notice gets to finish opening before Confirm is pressed. Pressed ~40 ms after it was read, Confirm closed it untaken.
SETTLE_SECONDS = 1
# How long the pointer rests on Confirm before the press, the way upstream's `_move_and_click` presses a button.
HOVER_SECONDS = 0.5
# The handler these run ahead of, so the warning never reaches it.
ANCHOR = "handle_center_confirm"

_patched = False


def handle_memory_limit(task):
    """Cancel the Faint Memory warning, then back out of the screen it was raised from.

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

    if time.monotonic() - (getattr(task, STATE, None) or float("-inf")) > BACK_OUT_WITHIN_SECONDS:
        return False
    # A reward or event removal offers Skip. The Dellang shop's removal has only Cancel in the same band.
    back_out = text_in_region(task, SKIP, BUTTON_REGION) or text_in_region(task, CANCEL, BUTTON_REGION)
    if back_out is None:
        return False
    task.log_info("Backing out of the pick that would have pushed Faint Memory past its limit")
    task.click_box(back_out)
    setattr(task, STATE, None)
    task.sleep(1)
    return True


def handle_divine_epiphany(task):
    """Accept the Faint Memory cost of a Divine Epiphany card, once the notice asking has settled.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if not text_in_region(task, DIVINE, WARNING_REGION):
        return False
    confirm = text_in_region(task, CONFIRM, CONFIRM_REGION)
    if confirm is None:
        task.log_info("Divine Epiphany notice on screen, but no Confirm button was read")
        return True
    task.log_info("Divine Epiphany card costs Faint Memory, confirming")
    task.sleep(SETTLE_SECONDS)
    task.move_relative(*centre_of(confirm, task.width, task.height))
    task.sleep(HOVER_SECONDS)
    task.click_box(confirm)
    task.sleep(1)
    return True


def apply():
    """Answer the Faint Memory dialogs wherever a mode would otherwise press their Confirm straight away."""
    global _patched
    if _patched:
        return
    register(lambda: insert_before(ANCHOR, handle_memory_limit))
    register(lambda: insert_before(ANCHOR, handle_divine_epiphany))
    _patched = True
