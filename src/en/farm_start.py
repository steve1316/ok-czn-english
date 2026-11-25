"""Let Farm Gaps and Farm Starting Card reroll Chaos's starting event on the Global client.

Upstream looks for a Chinese phrase in the starting event's options and, when it is missing, opens the Chaos Info menu to escape and start
over. On Global the phrase never matches, `handle_escape` cannot read the English button, and `handle_event_task` reads the open menu as
another event and taps its close button, so the menu opens and shuts forever.
"""

import re

from ok import Logger

from src.en.deck import GAP_KEY
from src.en.handlers import insert_before, loaded, register, wrap

logger = Logger.get_logger(__name__)

# Upstream's Farm Starting Card setting, the card to farm for. It wins when both farms are set.
INITIAL_CARD_KEY = "刷初始卡牌"
# The phrase each farm's starting-event check looks for, and how the Global option reads it. "Neutral RareLegendary Card" is another option.
PHRASES = {"移除2张": re.compile(r"remove\s*2\s*cards", re.IGNORECASE), "传说卡牌": re.compile(r"neutral\s*legendary", re.IGNORECASE)}
# The Chaos Info menu's button, read where upstream's `handle_escape` reads it. Kept out of `ocr.po`, which would also rewrite the card of that name.
ESCAPE = "escape"
ESCAPE_POINT = (0.952, 0.928)
# Marks the English reading in `handlers.wrap`, so it is installed once.
TAG = "english escape"

_patched = False


def farming_start(task, utils):
    """Tell whether the run is at Chaos's starting event with a farm on, mirroring upstream's own check in `handle_event_task`.

    Args:
        task: The running task, whose `node_status` says how far the run has got.
        utils: The loaded `utils` module, for its `_get_config_value`.

    Returns:
        True when a farm setting is on and no node has been cleared yet.
    """
    status = getattr(task, "node_status", None) or {}
    if status.get("pass_final_boss_count", 0) or status.get("node_count", 0):
        return False
    card = utils._get_config_value(task, INITIAL_CARD_KEY, "")
    return bool(isinstance(card, str) and card.strip()) or utils._get_config_value(task, GAP_KEY, False) is True


def marked(options):
    """Append upstream's phrase to each starting-event option whose English carries it, so upstream's own check picks it.

    Args:
        options: The options `recognize_event_options` read, each with its `description`.

    Returns:
        Copies of the options, with the phrase appended to any that match.
    """
    def mark(option):
        phrases = [phrase for phrase, pattern in PHRASES.items() if pattern.search(option["description"])]
        return {**option, "description": " ".join([option["description"], *phrases])}

    return [mark(option) for option in options]


def reading_english_escape(handler, utils):
    """Wrap `handle_escape` so it also taps the Global client's "Escape", which upstream looks for as the untranslated `逃脱`.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The loaded `utils` module, for its `find_box_at_point`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        if handler(task):
            return True
        button = utils.find_box_at_point(task, *ESCAPE_POINT)
        if button is None or button.name.strip().lower() != ESCAPE:
            return False
        logger.info("the Chaos Info menu is open, so the run escapes")
        task.click_box(button)
        task.node_status["is_escaped"] = True
        task.sleep(0.5)
        return True

    return wrapped


def handle_farm_escape(task):
    """Escape the Chaos Info menu a farm reroll opened.

    Args:
        task: The running task.

    Returns:
        True when the menu's Escape was tapped.
    """
    utils = loaded("utils")
    return farming_start(task, utils) and utils.handle_escape(task)


def install(utils):
    """Teach `handle_escape` the English button, and run it early while farming the start.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_escape", lambda handler: reading_english_escape(handler, utils), TAG)
    # The card reward and event handlers both claim the open menu before upstream's own escape, last in the list, is reached.
    insert_before("handle_card_reward", handle_farm_escape, only=("utils_chaos",))


def apply():
    """Let both farms reroll the starting event."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
