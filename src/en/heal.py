"""Take a Combatant in Deep Trauma to the Epione Center on the Global client, and always pay Credits there.

Upstream's Nightmare Mode check reads a Chinese title Global never draws, and it sits behind `handle_confirm`, so the run starts untreated.
Its Delete Memories confirm reads one label at a point Global's two-line label straddles, and the treatment ends on an English line it never
taps. It also spends a Communication Pass whenever one is held unless its pay-with-Credits switch is on, and that switch is off the card.
"""

from ok import Logger

from src.en.handlers import answering, insert_before, loaded, register, wrap
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

# Upstream's switch, read by `handle_trauma_center` in `utils_chaos`. `overrides.DROPPED` takes it off the card.
PAY_CREDITS = "优先使用金币治疗"
# Upstream's Treat Breakdown switch, which `handle_mental_breakdown` reads.
TREAT = "治疗崩溃"
# The Nightmare Mode banner names Deep Trauma only when a combatant needs treating, not when the player turned the mode on.
DEEP_TRAUMA = "deep trauma"
BANNER_REGION = (0.300, 0.020, 0.990, 0.110)
# The Nightmare Mode screen's Epione Center button. `ocr.po` already rewrites its English into this literal.
CENTER = "创伤中心"
CENTER_REGION = (0.000, 0.860, 0.250, 0.980)
# The confirm dialog's orange Delete Memories button, as (x1, y1, x2, y2). Its label wraps onto two lines.
DELETE_REGION = (0.507, 0.655, 0.811, 0.750)
# The line the treatment cutscene ends on.
DELETED = "memory deletion complete"
TAG = "always heals with Credits"
DELETE_TAG = "english delete memories"
DELETED_TAG = "english deletion complete"

_patched = False


def paying_credits(handler, utils_chaos):
    """Run upstream's Trauma Center handler with its pay-with-Credits switch read as on.

    Args:
        handler: `handle_trauma_center`, as currently installed.
        utils_chaos: Upstream's Chaos module, whose `_get_config_value` the handler reads the switch through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        with answering(utils_chaos, PAY_CREDITS, lambda task_, setting: True):
            return handler(task)

    return wrapped


def handle_deep_trauma(task):
    """Open the Epione Center from the Nightmare Mode screen while a Combatant is in Deep Trauma and Treat Breakdown is on.

    Args:
        task: The running Chaos task, whose `all_texts` holds the current OCR pass.

    Returns:
        True when it tapped the Epione Center button.
    """
    if text_in_region(task, DEEP_TRAUMA, BANNER_REGION) is None or not loaded("utils_chaos")._get_config_value(task, TREAT, True):
        return False
    button = text_in_region(task, CENTER, CENTER_REGION)
    if button is None:
        return False
    logger.info("a Combatant is in Deep Trauma, so the run visits the Epione Center first")
    task.click_box(button)
    task.sleep(1)
    return True


def reading_english(handler, needles, region, message):
    """Wrap an upstream handler so it also taps an English caption it cannot read.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        needles: Words that all have to be in `region`. The first one's box is tapped.
        region: Where to look, as (x1, y1, x2, y2).
        message: What to log when the fallback taps.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        if handler(task):
            return True
        boxes = []
        for needle in needles:
            boxes.append(text_in_region(task, needle, region))
            if boxes[-1] is None:
                return False
        logger.info(message)
        task.click_box(boxes[0])
        task.sleep(0.5)
        return True

    return wrapped


def pressing_delete(handler):
    """Wrap `handle_memory_elimination` so it presses the confirm's Delete Memories button.

    Args:
        handler: The handler to wrap, upstream's or another patch's.

    Returns:
        The wrapped handler.
    """
    return reading_english(handler, ("delete", "memories"), DELETE_REGION, "the Delete Memories confirm is pressed")


def tapping_through(handler):
    """Wrap `handle_treat_approve` so it taps past the treatment's last line.

    Args:
        handler: The handler to wrap, upstream's or another patch's.

    Returns:
        The wrapped handler.
    """
    return reading_english(handler, (DELETED,), (0.0, 0.0, 1.0, 1.0), "the treatment is done, so its last line is tapped")


def install(utils_chaos):
    """Wrap the Epione Center handlers and put the Nightmare Mode check ahead of Confirm, in Chaos only.

    Args:
        utils_chaos: Upstream's Chaos module, or None when it is not importable yet.
    """
    if utils_chaos is None:
        return
    wrap(utils_chaos, "handle_trauma_center", lambda handler: paying_credits(handler, utils_chaos), TAG)
    wrap(utils_chaos, "handle_memory_elimination", pressing_delete, DELETE_TAG)
    wrap(utils_chaos, "handle_treat_approve", tapping_through, DELETED_TAG)
    insert_before("handle_confirm", handle_deep_trauma, only=("utils_chaos",))


def apply():
    """Treat Deep Trauma at the Epione Center, always paying Credits."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils_chaos")))
    _patched = True
