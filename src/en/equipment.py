"""Offer equipment to the combatant the client itself recommends.

The Equipment screen marks one of the three rows "Recommended", and the mark is not decoration: it lands on
the combatant with a free slot of the kind the piece being offered fills. Upstream never reads it, because the
Chinese client the handlers were written against is read through the save-scum target instead. Where no target
is set - every Sortie run, since only Chaos carries the setting - the fallback is simply "whoever is listed
first", so the pick has always been arbitrary.

The banner is paired with a row by geometry rather than by guessing at the panel edges. It is drawn in the
top-right of its row's panel and that row's level tag sits below it, one measured gap away, with the next
row's tag a full row further down again. Taking the nearest tag *below* the banner therefore has most of a
row's height of slack in both directions, where taking the nearest tag either way would have had about a
third of that.

What changes is only which combatant is preferred, never whether the piece is worth installing. The banner is
put at the front of the level-tag list for the length of one `handle_equipment` call, which is exactly the
position upstream falls back to, so its own quality comparison still decides install-versus-give-away and a
save-scum target still outranks the banner wherever one is set.

One knock-on worth knowing when reading a log: upstream numbers combatants by their position in that list, so
on a frame where the banner moved a row, its `第N号主战员` counts from the recommended row rather than from the
top of the screen.
"""

from ok import Logger

from src.en.handlers import loaded, register, replace

logger = Logger.get_logger(__name__)

# The caption on the banner. `ocr.po` rewrites the client's "Recommended" into this literal.
RECOMMENDED = "推荐"
# Where the banner can appear, as (x1, y1, x2, y2). It is drawn over the combatant column on the right, so
# the left bound keeps the card being offered - which reaches to about 0.54 - out of the search.
BANNER_REGION = (0.560, 0.150, 1.000, 0.950)
# One row's pitch, measured off the captured screen as 241px of 1080. A tag further below the banner than
# this belongs to a lower row, not the banner's own.
ROW_PITCH = 0.223

_patched = False


def recommended_banner(task):
    """Find the client's "Recommended" banner in the current OCR pass.

    Args:
        task: The running task, whose `all_texts` holds that pass.

    Returns:
        The banner's box, or None when no row carries one.
    """
    x1, y1, x2, y2 = BANNER_REGION
    for box in getattr(task, "all_texts", None) or []:
        if RECOMMENDED not in box.name:
            continue
        center_x = (box.x + box.width / 2) / task.width
        center_y = (box.y + box.height / 2) / task.height
        if x1 <= center_x <= x2 and y1 <= center_y <= y2:
            return box
    return None


def recommended_row(task, banner, level_tags):
    """Say which combatant row the banner belongs to.

    Args:
        task: The running task, for the screen's size.
        banner: The banner's box, or None.
        level_tags: The level tags `_find_member_level_tags` found, top to bottom.

    Returns:
        The index of the banner's row, or None when it cannot be paired with one.
    """
    if banner is None or not level_tags:
        return None
    banner_y = (banner.y + banner.height / 2) / task.height
    nearest = None
    for index, tag in enumerate(level_tags):
        gap = (tag.y + tag.height / 2) / task.height - banner_y
        # Only a tag below the banner and inside the same row. A tag above belongs to the row before it, and
        # one a full pitch below belongs to the row after.
        if gap <= 0 or gap >= ROW_PITCH:
            continue
        if nearest is None or gap < nearest[1]:
            nearest = (index, gap)
    return nearest[0] if nearest else None


def preferring_recommended(handler, utils):
    """Wrap `handle_equipment` so the recommended combatant is the one it falls back to.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding `_find_member_level_tags`, the seam the order is changed through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        # Only the Equipment screen draws this, so its absence skips every other frame without repeating
        # upstream's page detection.
        banner = recommended_banner(task)
        if banner is None:
            return handler(task)
        original = utils._find_member_level_tags

        def preferred(*args, **kwargs):
            tags = original(*args, **kwargs)
            row = recommended_row(task, banner, tags)
            if not row:
                return tags
            logger.info(f"the client recommends combatant {row + 1} of {len(tags)}, so it is preferred")
            return [tags[row], *tags[:row], *tags[row + 1:]]

        utils._find_member_level_tags = preferred
        try:
            return handler(task)
        finally:
            utils._find_member_level_tags = original

    wrapped.__name__ = handler.__name__
    return wrapped


def apply():
    """Prefer the combatant the client recommends when nothing else has claimed the equipment."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None:
            return
        # Always wraps upstream's own handler, never a wrapper of it, so running twice cannot nest.
        replace("handle_equipment", preferring_recommended(utils.handle_equipment, utils))

    register(install)
    _patched = True
