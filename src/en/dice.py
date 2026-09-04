"""Reroll a failed dice roll instead of walking away from it.

Some event options are gated on a roll - "[Dexterous] Help with the work, Dice Roll 14, Upon success Spark a
Divine Epiphany" - and the game sells rerolls. Upstream has no notion of them: `handle_negotiation` sees the
failure screen and clicks Next. So this is a new handler rather than a change to an existing one, registered
immediately ahead of `handle_negotiation` so that declining a reroll falls through to upstream's Next click
with nothing else to arrange.

The reroll price is not on screen. OCR of that screen reads only the currency, the stat, the target number,
"Failure", "Reroll" and "Next" - the small cost badge beside the button never comes back as its own box - so
`REROLL_COST` is a constant here and the currency is read to make sure it can be paid.
"""

import re
import time

from ok import Logger

from src.en.handlers import insert_before, loaded, register

logger = Logger.get_logger(__name__)

# How many rerolls one roll is worth before taking the loss.
REROLL_CAP = 5
# What a reroll costs. Not readable from the screen, so it is stated here rather than guessed each frame.
REROLL_COST = 2

# Upstream reads the result caption at this point, and matches it against 失败.
RESULT_POINT = (0.498, 0.683)
FAILURE = "失败"
REROLL_LABEL = "reroll"

# The currency sits top right, drawn as "25/25" with a + button that OCR sometimes merges into the same box
# (seen as both "25/25+" and "25/25十"). Restricting to that corner keeps a health bar like "2536/2536"
# from being mistaken for it.
CURRENCY = re.compile(r"(\d+)\s*/\s*(\d+)")
CURRENCY_REGION = (0.75, 0.0, 1.0, 0.25)

# A roll that has not been seen for this long belongs to a past event, so the count starts again.
RESET_AFTER_SECONDS = 60
STATE = "_en_reroll"

_patched = False


def parse_currency(text):
    """Read the reroll currency out of a box.

    Args:
        text: The box text, such as `25/25+`.

    Returns:
        A `(current, maximum)` pair, or None when the text is not a currency reading.
    """
    found = CURRENCY.search(text or "")
    if not found:
        return None
    return int(found.group(1)), int(found.group(2))


def in_region(box, region, width, height):
    """Report whether a box's centre sits inside a relative region.

    Args:
        box: The OCR box.
        region: A `(left, top, right, bottom)` tuple in screen fractions.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        True when the box centre is inside the region.
    """
    left, top, right, bottom = region
    center_x = (box.x + box.width / 2) / width
    center_y = (box.y + box.height / 2) / height
    return left <= center_x <= right and top <= center_y <= bottom


def find_currency(boxes, width, height):
    """Find how many rerolls are left to spend.

    Args:
        boxes: Every OCR box on screen.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        A `(current, maximum)` pair, or None when the counter was not read.
    """
    for box in boxes:
        if not in_region(box, CURRENCY_REGION, width, height):
            continue
        parsed = parse_currency(box.name)
        if parsed:
            return parsed
    return None


def find_reroll_button(boxes):
    """Find the Reroll button.

    Args:
        boxes: Every OCR box on screen.

    Returns:
        The box, or None when it is not on screen.
    """
    return next((box for box in boxes if box.name.strip().casefold() == REROLL_LABEL), None)


def should_reroll(count, current, cost=REROLL_COST, cap=REROLL_CAP):
    """Decide whether to buy another roll.

    Args:
        count: Rerolls already spent on this roll.
        current: Reroll currency in hand.
        cost: What one reroll costs.
        cap: How many rerolls one roll is worth.

    Returns:
        True when another reroll is both allowed and affordable.
    """
    return count < cap and current >= cost


def read_state(task, now):
    """Read how many rerolls this roll has already had.

    Args:
        task: The running task.
        now: The current monotonic time.

    Returns:
        The count, restarted at zero when the last failure screen is too old to be the same roll.
    """
    count, last_seen = getattr(task, STATE, (0, 0.0))
    if now - last_seen > RESET_AFTER_SECONDS:
        return 0
    return count


def apply():
    """Reroll failed rolls wherever the failure screen is handled."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None:
            return
        insert_before("handle_negotiation", make_handler(utils))

    register(install)
    _patched = True


def make_handler(utils):
    """Build the reroll handler against the loaded task module.

    Args:
        utils: The imported `utils` module, passed in so the handler holds no import of its own.

    Returns:
        The handler function.
    """

    def handle_dice_reroll(task):
        result = utils.find_box_at_point(task, *RESULT_POINT)
        if not (result and result.name in FAILURE):
            return False

        now = time.monotonic()
        count = read_state(task, now)
        boxes = task.all_texts or []
        reroll_box = find_reroll_button(boxes)
        currency = find_currency(boxes, task.width, task.height)

        if reroll_box is None or currency is None:
            # Without both the button and the counter there is no safe way to spend, so take the loss.
            task.log_info("reroll unavailable: no Reroll button or reroll counter on screen")
            setattr(task, STATE, (0, now))
            return False

        current, maximum = currency
        if not should_reroll(count, current):
            task.log_info(
                f"not rerolling: {count} of {REROLL_CAP} used, {current}/{maximum} left, "
                f"each costs {REROLL_COST}"
            )
            setattr(task, STATE, (0, now))
            return False

        task.log_info(f"rerolling, attempt {count + 1} of {REROLL_CAP}, {current}/{maximum} left")
        task.click_box(reroll_box)
        setattr(task, STATE, (count + 1, now))
        task.sleep(1)
        return True

    return handle_dice_reroll
