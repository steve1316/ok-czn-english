"""Act on the kept combatant's row first when removing cards or sparking an Epiphany, and copy an AP card by default.

A Chaos run keeps one combatant - the save-scum target - and throws the other two away at the end, so anything
spent on the discarded pair is spent on nothing. Upstream can already find that row, but gates the rule on the
`刷空档` strategy being on and on the operation being a removal, so it almost never fires on this client. A copy
only takes cards on the user's list, and skips when none is on offer.
"""

from ok import Logger

from src.en import cards
from src.en.handlers import answering, loaded, register, standing_in, wrap

logger = Logger.get_logger(__name__)

# The runtime template `handle_archive_target_member` saves for the deck grid.
PORTRAIT = "target_member_in_select_card"
# Where that portrait is searched for, and how well it has to match. Upstream's own region and threshold.
PORTRAIT_REGION = (0.079, 0.092, 0.209, 0.675)
PORTRAIT_THRESHOLD = 0.6
# How far from the portrait a card still counts as being on its row. Upstream's own tolerance.
ROW_TOLERANCE = 0.25
# The strategy flag upstream gates its row rule on.
GAP_KEY = "刷空档"
# The operations worth steering. Duplicating is left alone, since a copy helps whoever holds the original.
ROW_ACTIONS = ("移除", "闪光", "灵光")
# Names this change in the shared record of what a function already carries.
TAG = "kept combatant's row"
# The operation and the setting a copy reads its cards from, and the tag its fallback carries.
COPY = "复制"
COPY_LIST = "复制卡牌列表"
COPY_TAG = "AP cards copied by default"

_patched = False


def portrait_of(task):
    """Find the kept combatant's portrait down the left of the deck grid.

    Args:
        task: The running task, which holds the runtime templates and the current frame.

    Returns:
        The portrait's match, or None when it was never captured or is not on screen.
    """
    if not task.feature_exists(PORTRAIT):
        return None
    return task.find_one(
        feature_name=PORTRAIT,
        box=task.box_of_screen(*PORTRAIT_REGION),
        threshold=PORTRAIT_THRESHOLD,
    ) or None


def row_of(task, portrait):
    """Say which height of the grid a portrait's row sits at.

    Args:
        task: The running task, for the screen's size.
        portrait: The portrait's match, or None.

    Returns:
        The row's centre height, normalised, or None when there is no portrait.
    """
    if portrait is None:
        return None
    return (portrait.y + portrait.height / 2) / task.height


def rows_first(cards, row_y):
    """Put the cards on one row ahead of the rest, without dropping any.

    Args:
        cards: The cards the deck recognizer found.
        row_y: The row's centre height, or None to leave the order alone.

    Returns:
        The cards, reordered.
    """
    if row_y is None:
        return cards
    # A stable sort on the boolean keeps the grid's own order within each group, which is what upstream's
    # bottom-up fallbacks expect to be handed.
    return sorted(cards, key=lambda card: abs(card["y"] - row_y) > ROW_TOLERANCE)


def preferring_target_row(select_card, utils):
    """Wrap `select_card` so the kept combatant's row is acted on first.

    Args:
        select_card: The function to wrap, upstream's or another patch's.
        utils: The module holding `_get_config_value` and `recognize_cards_in_deck`, the two seams.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        portrait = portrait_of(task) if action in ROW_ACTIONS else None
        row_y = row_of(task, portrait)
        if row_y is None:
            # Nothing to steer towards, so upstream runs exactly as it did. This is also what keeps the flag
            # from being answered on a frame where upstream's own row rule would have found no portrait.
            return select_card(task, card_names, count=count, action=action)
        logger.info(f"the kept combatant's row is at {row_y:.4f}, so {action} starts there")
        original_config = utils._get_config_value
        original_recognise = utils.recognize_cards_in_deck
        original_find_one = task.find_one

        def answering_gap(task_, key, default):
            # Only the row rule reads this inside `select_card`; every other reader is in another handler.
            if key == GAP_KEY:
                return True
            return original_config(task_, key, default)

        def ordered(*args, **kwargs):
            return rows_first(original_recognise(*args, **kwargs), row_y)

        def remembering(feature_name=None, *args, **kwargs):
            # Answering the flag makes upstream look this same portrait up again, up to twice, and a template
            # match over the portrait column is worth a few milliseconds each time.
            if feature_name == PORTRAIT:
                return portrait
            return original_find_one(feature_name, *args, **kwargs)

        with standing_in(utils, _get_config_value=answering_gap, recognize_cards_in_deck=ordered):
            with standing_in(task, find_one=remembering):
                return select_card(task, card_names, count=count, action=action)

    return wrapped


def with_ap_cards(names):
    """Add every card that gains AP after the cards the user named.

    Args:
        names: The cards to copy, from the `复制卡牌列表` setting.

    Returns:
        The user's cards first, then `cards.AP_CARDS` not already among them.
    """
    names = list(names or [])
    return names + [name for name in cards.AP_CARDS if name not in names]


def copying_ap_cards(select_card):
    """Wrap `select_card` so a copy that matches nothing on the user's list takes a card that gains AP.

    Args:
        select_card: The function to wrap, upstream's or another patch's.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        if action == COPY:
            card_names = with_ap_cards(card_names)
        return select_card(task, card_names, count=count, action=action)

    return wrapped


def choosing_ap_copies(choice, utils):
    """Wrap upstream's other copy screen, which reads the same setting itself, so it falls back to AP cards too.

    Args:
        choice: Upstream's `handle_copy_card_choice`.
        utils: The module holding `_get_config_value`, the seam it reads the setting through.

    Returns:
        The wrapped handler.
    """
    def handle_copy_card_choice(task):
        with answering(utils, COPY_LIST, lambda task_, value: with_ap_cards(value)):
            return choice(task)

    return handle_copy_card_choice


def install(utils):
    """Wrap `select_card` and the copy screen wherever the run reaches them.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "select_card", lambda select_card: preferring_target_row(select_card, utils), TAG)
    wrap(utils, "select_card", copying_ap_cards, COPY_TAG)
    wrap(utils, "handle_copy_card_choice", lambda choice: choosing_ap_copies(choice, utils), COPY_TAG)


def apply():
    """Start removals and Epiphanies on the row of the combatant the run is keeping, and copy AP cards by default."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
