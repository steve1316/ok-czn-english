"""Decide who gets a piece of equipment, what is worth buying, and refuse to pass over a Mythic one.

Four narrow changes inside `handle_equipment` and the shop. None copies a handler.

The Equipment screen marks the row with a free slot of the right kind "Recommended". Upstream never reads it,
picking by the save-scum target instead, or by whoever is listed first on every Sortie run since only Chaos
carries that setting. The banner is paired to a row by taking the nearest level tag *below* it, which leaves
most of a row's height of slack either way. Only the preference moves, so upstream's own quality comparison
still decides install-versus-give-away. A log trap follows from it: upstream numbers combatants by that list,
so `第N号主战员` counts from the recommended row rather than the top of the screen.

A Mythic is always worth taking, but upstream weighs the per-slot priority list ahead of quality, so a
configured piece already in the slot turns one away. Only that comparison is overridden. Not visible from
`ok_tasks/`: its top bucket already *is* Mythic here, because quality is read from one pixel of the item frame
and a Mythic's violet matches none of its constants and falls through to `传说`.

Equipment is bought only with `EQUIPMENT_FLOOR` credits in hand and only for a slot standing empty on somebody.
The shop shows no combatants, and upstream keeps only the save-data combatant's slots, so all three rows are
read off the install screen where they appear together. A run that has not reached it counts every slot bare,
which is the truth rather than a guess - a run opens with all three stripped.
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
SLOT_TAG = "every combatant's slots"
FLOOR_TAG = "equipment floor"

# Where the run keeps what it last saw of every combatant's three equipment slots, as a list per combatant.
# Upstream keeps the same thing for the save-data combatant alone, and only ever for the slot it is filling.
SLOTS = "_en_slots"
# The fewest credits worth spending on equipment. Below this the run leaves the shelf's equipment alone and
# keeps what it has for the cards, which are cheaper and which it can always use.
EQUIPMENT_FLOOR = 300
# What the colour read hands back for a slot with nothing in it. `None` means it could not see, which is a
# different thing and must not be read as room to spare.
EMPTY_SLOT = ""
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

    Upstream weighs the per-slot priority list before quality, so a configured piece already in the slot refuses
    anything not on that list, a Mythic included. A Mythic outranks any list entry, since there is no way to get a
    better one and only one may be worn at a time. The override stops at a slot already holding a Mythic, where
    swapping gains nothing, and upstream's one-per-combatant rule still runs after this.

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


def bare_slots(task):
    """Say which equipment slots are still empty on somebody.

    Args:
        task: The running task.

    Returns:
        The slot numbers standing empty on at least one combatant. Every slot when no equipment screen has
        been seen yet, which is not merely permissive - a run opens with all three combatants stripped.
    """
    remembered = getattr(task, SLOTS, None)
    if not remembered:
        return {0, 1, 2}
    return {slot for member in remembered
            for slot, quality in enumerate(member) if quality == EMPTY_SLOT}


def remembering_slots(handler, utils):
    """Wrap `handle_equipment` so every combatant's slots are read, not only the one being equipped.

    The install screen is the one place all three are on screen at once, and upstream is already there with
    their rows in hand - it just reads the slots of whichever combatant it is about to equip and throws the
    other two rows away. Reading all three costs three pixel probes each and is the only way the shop, which
    shows no combatants at all, can know whether a piece would fill a gap or replace something.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module whose row reader and colour reader the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        find_rows, read_slots = utils._find_member_level_tags, utils._member_equipment_qualities
        rows = []

        def recorded(task_, *args, **kwargs):
            # The first read is the combatant column. The handler makes no other, and taking the first is
            # steadier than matching the page label it passes, which only ever reaches a log.
            found = find_rows(task_, *args, **kwargs)
            if not rows and found:
                rows.extend(found)
            return found

        with standing_in(utils, _find_member_level_tags=recorded):
            handled = handler(task)
        if rows:
            setattr(task, SLOTS, [read_slots(task, row) for row in rows])
        return handled

    return wrapped


def refusing_equipment(handler, utils):
    """Wrap `handle_shop` so equipment is only bought to fill a slot nobody has filled, with money to spare.

    Upstream buys any equipment its priority list names and the run can afford, which spends a run's credits
    on replacing gear it is already wearing. Both conditions are asked for rather than derived: the run holds
    real money, and the piece has somewhere bare to go.

    Withholding the list rather than intercepting the click is what keeps the rest of upstream's shop intact
    - it simply finds no match and moves on to the cards, or leaves.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module whose priority reader and credit reader the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        priority = utils._equipment_priority

        def gated(task_, slot):
            listed = priority(task_, slot)
            # Read after the list, so a slot nothing is offered for costs no reading at all.
            if not listed:
                return listed
            credit = utils._get_current_credit(task_)
            if credit < EQUIPMENT_FLOOR:
                logger.info(f"holding {credit} credits, so the shelf's equipment is left where it is")
                return []
            if slot not in bare_slots(task_):
                logger.info(f"slot {slot + 1} is filled on every combatant, so its equipment is left")
                return []
            return listed

        with standing_in(utils, _equipment_priority=gated):
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
    wrap(utils, "handle_equipment", lambda handler: remembering_slots(handler, utils), SLOT_TAG)
    wrap(utils, "handle_shop", lambda handler: refusing_equipment(handler, utils), FLOOR_TAG)


def apply():
    """Prefer the recommended combatant, and never pass over a Mythic piece."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
