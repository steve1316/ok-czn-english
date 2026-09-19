"""Decide who gets a piece of equipment, what is worth buying, and refuse to pass over a Mythic one.

Six narrow changes inside `handle_equipment`, the shop and the Tasks tab. None copies a handler. The Equipment
screen marks the row with a free slot of the right kind "Recommended", and upstream never reads it - it picks
by the save-scum target instead, or by whoever is listed first on every Sortie run, since only Chaos carries
that setting.
"""

from ok import Logger

from src.en import rewards
from src.en.dashboard import TEAM_GEAR
from src.en.handlers import StandIn, loaded, register, standing_in, wrap
from src.en.rewards import EQUIPMENT_KEYS
from src.en.screen import COMBATANT_NAME_POINTS, combatant_names, combatant_slot_points, text_in_region
from src.en.state import GEAR, say_once

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
# The violet the client frames a Mythic slot in, as (red, green, blue). Measured off the Equipment screen,
# where all six Mythic slots two captures showed sat within three of it, and no other slot within ninety.
# Nothing in `ok_tasks/` has a constant for it - upstream names Normal and Epic and calls the rest Mythic.
MYTHIC_RGB = (137, 82, 164)
# Names each change in the shared record of what a function already carries.
RECOMMENDED_TAG = "recommended combatant"
MYTHIC_TAG = "mythic equipment"
SLOT_TAG = "every combatant's slots"
PLACEMENT_TAG = "mythic placement"
TEAM_GEAR_TAG = "team equipment"


# Where the run keeps what it last saw of every combatant's three equipment slots, as a list per combatant.
# Upstream keeps the same thing for the save-data combatant alone, and only ever for the slot it is filling.
SLOTS = "_en_slots"
# The credits a shop visit needs in hand to start buying generated equipment. Below this, without a spree already
# open, the run leaves the shelf's equipment alone and keeps what it has for the cards.
SPREE_START = 600
# Where an open spree stops. Inclusive: at exactly this many credits the spree is over.
SPREE_END = 300
# Where the run keeps the shop visit its spree belongs to, so the spree ends with the visit.
SPREE = "_en_spree"
# What the colour read hands back for a slot with nothing in it. `None` means it could not see, which is a
# different thing and must not be read as room to spare.
EMPTY_SLOT = ""
# What a slot with nothing in it is called in the Tasks tab's row. A dash rather than a word, because most of
# the nine slots read this way early in a run and the row scans better when only what is worn carries a name.
EMPTY_TIER = "-"
# What the top bucket is called once a colour has confirmed it, and what an unconfirmed one is called instead.
# Upstream has no second answer - folding the unplaceable into its top bucket is how a toast-dimmed slot came
# to read as the rarest thing in the game.
MYTHIC_TIER = "Mythic"
UNKNOWN_TIER = "?"
# What each of upstream's own quality buckets is called on this client, where every one of its names is a tier
# out. Thirteen pieces the logs name, checked against the client's own rarity table: `普通` is RARE, `史诗` is
# LEGEND, and `传说` is UNIQUE - which the client itself calls Mythic in the only line where it names a tier,
# so that is the word the row uses. The top bucket is missing on purpose: upstream puts every colour it cannot
# place there, so it is the one answer that has to be checked rather than translated.
BUCKET_TIERS = {EMPTY_SLOT: EMPTY_TIER, "普通": "Rare", "史诗": "Legend"}
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

    Paired by taking the nearest level tag below the banner, which leaves most of a row's height of slack
    either way. A log trap follows: upstream numbers combatants by that same list, so `第N号主战员` counts
    from the recommended row rather than from the top of the screen.

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


def is_mythic_colour(utils, rgb):
    """Say whether an equipment slot's frame colour is the violet the client draws around a Mythic piece.

    Args:
        utils: The module carrying the colour compare, so the tolerance stays upstream's one.
        rgb: The colour read off the slot, or None when it could not be read.

    Returns:
        True only on a positive match, so an unreadable slot is never one.
    """
    return utils._rgb_is_close(rgb, MYTHIC_RGB)


def has_room_for_mythic(utils, colours, slot):
    """Say whether a combatant could legally take the Mythic on offer.

    Decided by matching `MYTHIC_RGB` outright rather than by upstream's top bucket, which is only reliable in
    one direction: every Mythic lands in it, but so does any slot too dim to match a constant - an empty slot
    at `RGB=(24, 37, 46)` read as one, and the toast drawn over a refused click dims a whole row into it.

    Args:
        utils: The module carrying the colour compare.
        colours: That combatant's three slot frame colours, in slot order.
        slot: The slot the piece on offer belongs in.

    Returns:
        True unless a Mythic already sits in one of the other two slots. One in the slot being filled is only a
        swap, which leaves the combatant wearing the single Mythic the client allows.
    """
    return not any(index != slot and is_mythic_colour(utils, rgb) for index, rgb in enumerate(colours))


def slot_colours(task, utils, rows):
    """Read the frame colour of every combatant's three equipment slots.

    Upstream's row reader already probes those points and throws the colours away behind a quality bucket.
    Borrowing it, rather than measuring the offsets again here, keeps the positions upstream's own.

    Args:
        task: The running task, holding the frame to read.
        utils: The module carrying the row reader and the colour probe.
        rows: The combatants' level tags, which the offsets are measured from.

    Returns:
        One list of three colours per row, in slot order. An entry is None where the slot could not be read.
    """
    original = utils._equipment_quality_at
    row_colours = []

    def probed(task_, point, allow_empty=False):
        quality, rgb = original(task_, point, allow_empty)
        row_colours[-1].append(rgb)
        return quality, rgb

    with standing_in(utils, _equipment_quality_at=probed):
        for row in rows:
            row_colours.append([])
            utils._member_equipment_qualities(task, row)
    return row_colours


def slot_tier(task, utils, point):
    """Name the tier held in the equipment slot framed at a point.

    Args:
        task: The running task, holding the frame to read.
        utils: The module carrying the colour read, whose buckets and tolerances are upstream's own.
        point: Where on the slot's frame to sample, as `(x, y)` in screen fractions.

    Returns:
        The client's name for that tier, or `UNKNOWN_TIER` for a colour upstream could not place and the
        Mythic violet does not match either.
    """
    quality, rgb = utils._equipment_quality_at(task, point, allow_empty=True)
    if quality in BUCKET_TIERS:
        return BUCKET_TIERS[quality]
    return MYTHIC_TIER if is_mythic_colour(utils, rgb) else UNKNOWN_TIER


def team_equipment(task, utils):
    """Read every combatant's three equipment slots off the Combatants screen.

    Args:
        task: The running task, holding the frame to read.
        utils: The module carrying the colour read.

    Returns:
        One `"<tier>/<tier>/<tier>"` line per combatant, left to right, so a line's place in the list is which
        combatant it belongs to. Empty when not one slot on the screen could be read, because a frame that
        gave nothing must leave the row saying what it already said rather than overwrite it with unknowns.
    """
    columns = [[slot_tier(task, utils, point) for point in combatant_slot_points(column)]
               for column in range(len(COMBATANT_NAME_POINTS))]
    if all(tier == UNKNOWN_TIER for tiers in columns for tier in tiers):
        return []
    return ["/".join(tiers) for tiers in columns]


def reading_the_team_gear(handler, utils, utils_chaos):
    """Wrap `handle_archive_target_member` so the team's gear is read while its page is still open.

    The capture's last act is to tap the page closed and sleep a second, and `all_texts` survives that while
    `frame` does not - a read afterwards gets the names off the held OCR pass and the pixels off whatever the
    client has drawn since, which reported nine slots as empty and unknown. Riding its taps puts the read back
    on the frame it was looking at. The first tap made while all three names are on screen is the one: the tap
    before it selects the tab and happens ahead of the capture's own OCR, so the names are not all there yet.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module carrying the name and colour reads.
        utils_chaos: The module the capture taps through, which is the seam the read rides.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original = utils_chaos._move_and_click
        worn = []

        def tapped(task_, x, y):
            names = [] if worn else combatant_names(task_, utils)
            if names and all(names):
                worn.append(", ".join(team_equipment(task_, utils)))
                setattr(task_, TEAM_GEAR, worn[0])
                logger.info(f"the team is wearing {worn[0]}")
            return original(task_, x, y)

        with standing_in(utils_chaos, _move_and_click=tapped):
            handled = handler(task)
        if handled and not worn:
            # Loud on purpose. The read is placed by shape rather than by name, so a capture that stops
            # tapping while its names are up would leave the row quietly saying what it said before.
            logger.warning("the Combatants page was captured without its equipment being read, so the "
                           "Equipment row keeps what it had")
        return handled

    return wrapped


def offering_mythic_where_it_fits(handler, utils):
    """Wrap `handle_equipment` so a Mythic is only ever offered to a combatant that can wear it.

    Rows are withheld rather than the click intercepted, because upstream already knows what to do with each
    case. Fewer rows and it picks among the ones left. None at all and it extracts the piece, or cancels when a
    shop is the one offering it. All three are the right answer, and none needs a handler of its own.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding `_equipment_info` and `_find_member_level_tags`, the seams this reads through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        read_info, find_rows = utils._equipment_info, utils._find_member_level_tags
        slot = None

        def noted(task_, *args, **kwargs):
            nonlocal slot
            info = read_info(task_, *args, **kwargs)
            if info:
                slot = info["slot"]
            return info

        def fitting(task_, *args, **kwargs):
            rows = find_rows(task_, *args, **kwargs)
            # Read here rather than up front: this is only reached on a confirmed install-equipment page, and
            # the rows are only worth probing for a piece the one-per-combatant rule applies to at all.
            if not rows or slot is None or not mythic_offer(task_):
                return rows
            fits = [row for row, colours in zip(rows, slot_colours(task_, utils, rows))
                    if has_room_for_mythic(utils, colours, slot)]
            if len(fits) < len(rows):
                logger.info(f"{len(rows) - len(fits)} of {len(rows)} combatants already wear a Mythic outside slot {slot + 1}, so this one is not offered to them")
            return fits

        with standing_in(utils, _equipment_info=noted, _find_member_level_tags=fitting):
            return handler(task)

    return wrapped


class RecommendedChoice(StandIn):
    """Stands in for `random` while the equipment handler runs, so a random pick of combatants takes the recommended one.

    Upstream hands whatever the save-data combatant turns down to `random.choice` of the other rows. Anything
    that is not a list holding the recommended row falls through to the real module.
    """

    # The recommended row's level tag, once the handler has read the rows. A class attribute, so the lookup never
    # reaches `StandIn.__getattr__`.
    row = None

    def choice(self, sequence):
        """Take the recommended row when it is on offer, otherwise defer to the real module.

        Args:
            sequence: Whatever upstream is choosing between.

        Returns:
            One item from the sequence.
        """
        # By identity: the rows upstream chooses from are the same tag boxes the row reader handed it.
        if self.row is not None and any(item is self.row for item in sequence):
            logger.info("giving it to the recommended combatant rather than a random one")
            return self.row
        return self.original.choice(sequence)


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
    """Wrap `handle_equipment` so the recommended combatant is the one it gives to.

    It becomes the row upstream falls back to, and for a piece the user's priority list does not name, the row
    the save-data combatant stands down in favour of. A named piece, and a Mythic, still go where upstream's
    own comparison sends them. Sortie is left alone, having no save-data combatant to stand down.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module holding the row reader, the save-data binding, the install decision and `random`.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        read_rows, bind = utils._find_member_level_tags, utils._find_target_member_index
        decide = utils._should_install_equipment
        chooser = RecommendedChoice(utils.random)
        recommended, bound = [], []

        def preferred(task_, *args, **kwargs):
            tags = read_rows(task_, *args, **kwargs)
            # Read here rather than up front: upstream calls this once, on a confirmed install-equipment page,
            # so the banner is looked for on those frames instead of on every frame of the run. Reading the
            # task from the call rather than closing over the outer one also keeps a 6MB frame from being
            # captured by anything that outlives this call.
            row = recommended_row(task_, recommended_banner(task_), tags)
            if row is not None:
                chooser.row = tags[row]
                recommended.append(row)
            if not row:
                # Row 0 too: it is already where upstream falls back to, so there is nothing to move.
                return tags
            logger.info(f"the client recommends combatant {row + 1} of {len(tags)}, so it is preferred")
            return [tags[row], *tags[:row], *tags[row + 1:]]

        def noted(task_, *args, **kwargs):
            index = bind(task_, *args, **kwargs)
            bound.append(index)
            return index

        def decided(task_, current_name, current_quality, new_equipment):
            install, reason = decide(task_, current_name, current_quality, new_equipment)
            if not install or new_equipment.get("rank") is not None or not recommended:
                return install, reason
            # Nothing to stand down for in a mode carrying no save-data combatant, which falls to the banner
            # already, nor for a Mythic, whose banner row may have been dropped for having no room.
            if "刷存档主战员" not in getattr(task_, "default_config", {}) or mythic_offer(task_):
                return install, reason
            # The reorder above leaves the banner's row first, so a save-data combatant bound anywhere else is
            # one the banner is not on. Unbound, upstream gives the piece away without being asked to.
            if not bound or bound[-1] in (None, 0):
                return install, reason
            logger.info(f"the client recommends another combatant and the priority list does not name this "
                        f"piece, so the save-data combatant stands down: {reason}")
            return False, "the client recommends another combatant"

        with standing_in(utils, _find_member_level_tags=preferred, _find_target_member_index=noted,
                         _should_install_equipment=decided, random=chooser):
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


def on_spree(task, credit):
    """Open, hold or close this shop visit's equipment spree.

    Args:
        task: The running task. The spree is kept on it, keyed by the run and the node the shop is on.
        credit: The credits the shop screen shows now.

    Returns:
        True while the spree is open.
    """
    status = getattr(task, "node_status", None) or {}
    visit = (getattr(task, "start_time", None), status.get("pass_final_boss_count"), status.get("node_count"))
    if credit <= SPREE_END:
        setattr(task, SPREE, None)
        return False
    if getattr(task, SPREE, None) == visit:
        return True
    if credit >= SPREE_START:
        setattr(task, SPREE, visit)
        return True
    return False


def buying_on_spree(generate, utils_of):
    """Wrap `rewards.generated_list` so a generated equipment list only offers anything on a spree, for a bare slot.

    Upstream buys any equipment its priority list names and the run can afford, which spends a run's credits
    on replacing gear it is already wearing. Gating the generated list, rather than the list the shop reads, is what
    leaves a list the user configured alone - it never passes through here. Withholding the list rather than
    intercepting the click keeps the rest of upstream's shop intact: it finds no match and refreshes, or leaves.

    Args:
        generate: The list builder to wrap, `rewards`' own.
        utils_of: Returns the loaded `utils` module, whose credit reader the shop's own reading goes through.

    Returns:
        The wrapped builder.
    """
    def generated(task, key, farmed=""):
        listed = generate(task, key, farmed)
        slot = EQUIPMENT_KEYS.get(key)
        # Read after the list, so a slot nothing is offered for costs no reading at all.
        if slot is None or not listed:
            return listed
        credit = utils_of()._get_current_credit(task)
        if not on_spree(task, credit):
            say_once(task, GEAR, f"{credit} credits and no spree open, so the shelf's equipment is left")
            return []
        if slot not in bare_slots(task):
            say_once(task, GEAR, f"slot {slot + 1} is filled on every combatant, so its equipment is left")
            return []
        say_once(task, GEAR, f"slot {slot + 1} is bare and there are {credit} credits, "
                             f"so the shelf's equipment is on offer until {SPREE_END}")
        return listed

    return generated


def install(utils, utils_chaos=None):
    """Wrap the equipment handler wherever the run reaches it, and the capture the team is read from.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
        utils_chaos: The loaded `utils_chaos` module, which carries the capture the team is read off. Left
            out or None until it is imported, and on a load that never imports it there is no capture to ride.
    """
    if utils_chaos is not None and utils is not None:
        wrap(utils_chaos, "handle_archive_target_member",
             lambda handler: reading_the_team_gear(handler, utils, utils_chaos), TEAM_GEAR_TAG)
    if utils is None:
        return
    # First, which puts its row reader innermost of the three that stand in for one, so the rows it drops are
    # dropped last - after `remembering_slots` has recorded every combatant the screen actually shows.
    wrap(utils, "handle_equipment", lambda handler: offering_mythic_where_it_fits(handler, utils), PLACEMENT_TAG)
    wrap(utils, "handle_equipment", lambda handler: preferring_recommended(handler, utils), RECOMMENDED_TAG)
    wrap(utils, "handle_equipment", lambda handler: insisting_on_mythic(handler, utils), MYTHIC_TAG)
    wrap(utils, "handle_equipment", lambda handler: remembering_slots(handler, utils), SLOT_TAG)


def apply():
    """Prefer the recommended combatant, place or extract a Mythic, buy on a spree, and report what is worn."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils"), loaded("utils_chaos")))
    rewards.generated_list = buying_on_spree(rewards.generated_list, lambda: loaded("utils"))
    _patched = True
