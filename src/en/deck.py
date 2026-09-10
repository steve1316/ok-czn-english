"""Act on the kept combatant's row first when removing cards or sparking an Epiphany.

A Chaos run picks one combatant to keep - the save-scum target - and throws the other two away at the end.
Anything spent on the discarded pair is spent on nothing, so the kept combatant's row of the deck grid is the
one worth removing from and the one worth sparking.

Upstream can already find that row. `handle_archive_target_member` crops the target's portrait from the
information screen at the start of a run and saves it as a runtime template, and `select_card` matches it down
the left of the deck grid and prefers cards at the same height. Two conditions keep that from firing: it is
gated on the `刷空档` strategy being switched on, and on the operation being a removal.

Both are widened here, for the length of one `select_card` call:

**Removing.** The strategy flag is answered True, which is all that stands between the row rule and every
removal. Upstream's own code then does the work, tolerance and all. That flag is read in three other places,
none of them reachable from `select_card`, so answering it here reaches nothing else.

**Sparking an Epiphany.** Upstream has no row rule for this operation, and its fallbacks re-sort the grid by
height whatever they are handed, so the only order that survives is the one its priority-list pass walks. The
grid is therefore reordered rather than filtered: where several cards match the user's Epiphany list, the kept
combatant's are reached first. Where none match, upstream's own bottom-up fallback still decides, and nothing
is filtered away, so a row holding no eligible card can never strand the run.

Both changes stand down when the portrait was never captured, which is every Sortie run and any Chaos run that
has not reached the information screen yet.
"""

from ok import Logger

from src.en.handlers import loaded, register

logger = Logger.get_logger(__name__)

# The runtime template `handle_archive_target_member` saves for the deck grid.
PORTRAIT = "target_member_in_select_card"
# Where that portrait is searched for, as (x1, y1, x2, y2) - upstream's own region.
PORTRAIT_REGION = (0.079, 0.092, 0.209, 0.675)
# How far from the portrait a card still counts as being on its row. Upstream's own tolerance.
ROW_TOLERANCE = 0.25
# The strategy flag upstream gates its row rule on.
GAP_KEY = "刷空档"
# The operations worth steering. Duplicating is left alone, since a copy helps whoever holds the original.
ROW_ACTIONS = ("移除", "闪光", "灵光")

_patched = False


def target_row_y(task):
    """Find the height of the kept combatant's row in the deck grid.

    Args:
        task: The running task, which holds the runtime templates and the current frame.

    Returns:
        The row's centre height, normalised, or None when the portrait is not on screen.
    """
    if not task.feature_exists(PORTRAIT):
        return None
    found = task.find_one(
        feature_name=PORTRAIT,
        box=task.box_of_screen(*PORTRAIT_REGION),
        threshold=0.6,
    )
    if not found:
        return None
    return (found.y + found.height / 2) / task.height


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
    on_row = [c for c in cards if abs(c["y"] - row_y) <= ROW_TOLERANCE]
    return on_row + [c for c in cards if abs(c["y"] - row_y) > ROW_TOLERANCE] if on_row else cards


def preferring_target_row(select_card, utils):
    """Wrap `select_card` so the kept combatant's row is acted on first.

    Args:
        select_card: The function to wrap, upstream's or another patch's.
        utils: The module holding `_get_config_value` and `recognize_cards_in_deck`, the two seams.

    Returns:
        The wrapped function.
    """
    def wrapped(task, card_names, count=1, action=""):
        if action not in ROW_ACTIONS:
            return select_card(task, card_names, count=count, action=action)
        row_y = target_row_y(task)
        if row_y is not None:
            logger.info(f"the kept combatant's row is at {row_y:.4f}, so {action} starts there")
        original_config = utils._get_config_value
        original_recognise = utils.recognize_cards_in_deck

        def answering_gap(task_, key, default):
            # Only the row rule reads this inside `select_card`; every other reader is in another handler.
            if key == GAP_KEY:
                return True
            return original_config(task_, key, default)

        def ordered(*args, **kwargs):
            return rows_first(original_recognise(*args, **kwargs), row_y)

        utils._get_config_value = answering_gap
        utils.recognize_cards_in_deck = ordered
        try:
            return select_card(task, card_names, count=count, action=action)
        finally:
            utils._get_config_value = original_config
            utils.recognize_cards_in_deck = original_recognise

    wrapped.__name__ = select_card.__name__
    return wrapped


def apply():
    """Start removals and Epiphanies on the row of the combatant the run is keeping."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None or getattr(utils.select_card, "_en_prefers_target_row", False):
            return
        wrapped = preferring_target_row(utils.select_card, utils)
        wrapped._en_prefers_target_row = True
        utils.select_card = wrapped
        logger.info(f"{', '.join(ROW_ACTIONS)} will start on the kept combatant's row")

    register(install)
    _patched = True
