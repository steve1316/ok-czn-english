"""Decide who gets a piece of equipment, and refuse to pass over a Mythic one.

Two fork-local changes to `handle_equipment`, both narrow: one moves which combatant is preferred, the other
moves one comparison. Neither copies any of the handler.

**Who gets it.**

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

**Mythic pieces.** Only one may be worn per combatant and there is nothing better to hold out for, so one is
always worth taking. Upstream weighs the user's per-slot priority list ahead of quality, though, which means
a configured piece already in the slot turns a Mythic away. That one comparison is overridden while a Mythic
is on offer.

Worth recording, because it is not obvious from `ok_tasks/`: upstream's top quality bucket already *is*
Mythic on this client. It reads quality from a single pixel of the item's frame, and the violet a Mythic
draws is the one colour that matches none of its constants and falls through to `传说`. So the existing
one-per-combatant rule and the existing top ranking both apply to Mythic pieces already, and only the
priority-list comparison needed moving.
"""

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap
from src.en.screen import text_in_region

logger = Logger.get_logger(__name__)

# The caption on the banner. `ocr.po` rewrites the client's "Recommended" into this literal.
RECOMMENDED = "推荐"
# Where the banner can appear, as (x1, y1, x2, y2). It is drawn over the combatant column on the right, so
# the left bound keeps the card being offered - which reaches to about 0.54 - out of the search.
BANNER_REGION = (0.560, 0.150, 1.000, 0.950)
# One row's pitch, measured off the captured screen as 241px of 1080. A tag further below the banner than
# this belongs to a lower row, not the banner's own.
ROW_PITCH = 0.223

# The caption the client prints under a Mythic piece. Matched in English because nothing in `ok_tasks/` looks
# for it, so there is no Chinese literal for the catalog to rewrite it into.
MYTHIC = "mythic"
# Where that caption sits, as (x1, y1, x2, y2). Under the offered piece on the left, well clear of the
# combatant column, where item names would otherwise supply the same word.
MYTHIC_REGION = (0.050, 0.660, 0.600, 0.800)
# Names each change in the shared record of what a function already carries.
RECOMMENDED_TAG = "recommended combatant"
MYTHIC_TAG = "mythic equipment"
# Upstream's top quality bucket. Nothing in `ok_tasks/` knows the word Mythic, but the colour it reads off a
# Mythic piece - a violet no other tier uses - is the one that falls through to this, so the two coincide.
TOP_QUALITY = "传说"

_patched = False


def recommended_banner(task):
    """Find the client's "Recommended" banner in the current OCR pass.

    Args:
        task: The running task, whose `all_texts` holds that pass.

    Returns:
        The banner's box, or None when no row carries one.
    """
    return text_in_region(task, RECOMMENDED, BANNER_REGION)


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


def mythic_offer(task):
    """Report whether the piece on offer is Mythic.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        True when the client's one-per-combatant caption is under the offered piece.
    """
    return text_in_region(task, MYTHIC, MYTHIC_REGION) is not None


def insisting_on_mythic(handler, utils):
    """Wrap `handle_equipment` so a Mythic piece is never passed over for a configured one.

    Upstream weighs the user's per-slot priority list before quality, so a configured piece already in the
    slot refuses anything not on that list - a Mythic included. A Mythic is worth more than any list entry,
    because there is no way to obtain a better one and only one may be worn at a time.

    The override stops at the slot already holding a Mythic. Swapping one for another gains nothing, and
    upstream's own one-per-combatant rule runs after this and still moves the piece to another combatant when
    the preferred one is already wearing one.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding `_should_install_equipment`, the seam the decision is changed through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original = utils._should_install_equipment

        def insisted(task_, current_name, current_quality, new_equipment):
            install, reason = original(task_, current_name, current_quality, new_equipment)
            # Read here rather than up front: this is only reached on a confirmed equipment page, where the
            # caption is worth looking for, instead of on every frame of the run.
            if install or current_quality == TOP_QUALITY or not mythic_offer(task_):
                return install, reason
            logger.info(f"taking a Mythic over the configured piece, which upstream refused: {reason}")
            return True, "Mythic outranks the configured equipment"

        with standing_in(utils, _should_install_equipment=insisted):
            return handler(task)

    return wrapped


def preferring_recommended(handler, utils):
    """Wrap `handle_equipment` so the recommended combatant is the one it falls back to.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding `_find_member_level_tags`, the seam the order is changed through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original = utils._find_member_level_tags

        def preferred(task_, *args, **kwargs):
            tags = original(task_, *args, **kwargs)
            # Read here rather than up front: upstream calls this once, on a confirmed install-equipment page,
            # so the banner is looked for on those frames instead of on every frame of the run. Reading the
            # task from the call rather than closing over the outer one also keeps a 6MB frame from being
            # captured by anything that outlives this call.
            row = recommended_row(task_, recommended_banner(task_), tags)
            if not row:
                # Row 0 too: it is already where upstream falls back to, so there is nothing to move.
                return tags
            logger.info(f"the client recommends combatant {row + 1} of {len(tags)}, so it is preferred")
            return [tags[row], *tags[:row], *tags[row + 1:]]

        with standing_in(utils, _find_member_level_tags=preferred):
            return handler(task)

    return wrapped


def install(utils):
    """Wrap the equipment handler wherever the run reaches it.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_equipment", lambda handler: preferring_recommended(handler, utils), RECOMMENDED_TAG)
    wrap(utils, "handle_equipment", lambda handler: insisting_on_mythic(handler, utils), MYTHIC_TAG)


def apply():
    """Prefer the recommended combatant, and never pass over a Mythic piece."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
