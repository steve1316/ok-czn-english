"""Read and steer Season 4's Desire cards.

Reaching three, five or seven points in one faction unlocks a team-wide bonus, so concentrating beats
spreading across four. That is what the target-faction setting is for.

The tag is the whole state. The client prints it on the card - `[ Inquiry ]`, `[ Inquiry 2 ]`, or
`[ Control / Inquiry 2 ]` once two factions have merged - so faction and points are both on screen and the
points total is the card's level. Nothing has to be remembered between frames, which matters because a run can
be resumed, or the bot restarted, part way through a node.

Reading it is the hard part. The tag shares a region with the effect text below it, and the reader loses
brackets, drops spaces, and sometimes glues the tag onto the sentence under it - one captured frame produced
`Control200% Damage to all...`. So the shape is tested rather than searched: a reading counts as a tag only
when everything in it is a faction name, a number, or bracket-and-slash punctuation, and its points add up to
a level a card can reach. That turns away a mangled tag and a sentence that merely contains the word Control.
The asymmetry is the point - turning away a real tag costs one frame of a screen re-read every second, while
acting on a misread one steers every card pick for the rest of the run.

Most Desire cards arrive on a screen that is not a Desire screen. An event granting one drops the run onto the
ordinary card assign screen, which decides on the reward priority list alone, and a Desire card is named for
its effect so the list never names it - a real run pressed Skip on two in four minutes. That screen is claimed
here too, but only far enough to tell upstream the card is worth keeping.

The Desire screen and the assign screen are one decision, not two. Taking a card on the first drops the run
onto the second to hand it over, and judging the faction again there threw away what the first had just
chosen: a real run picked `Knowledge Addiction` off three cards, none of the faction being chased, then
skipped it four seconds later. So a Desire screen leaves the name of what it took on the task and the assign
screen honours it. The purchase guard still outranks that - nothing here ever spends credits.

A combatant already holding three points gains nothing from another card, but upstream hands it to the save-data
combatant or the first row regardless. A full row is made to read as "Unobtainable" to upstream, which keeps the
rows where they are - upstream binds the save-data combatant by row position. With nobody left the screen is
rerolled, then skipped.

The points are read off the "Lv. N" printed on the Desire card a combatant holds, not the faction badges. On two
captures OCR read none of three badge "1"s but read that digit at 1.00, and the badges also preview the card on
the selected row. A missed digit counts as room, which is upstream's old behaviour.
"""

import re
from types import SimpleNamespace

from ok import Logger

from src.en.handlers import insert_before, loaded, register, standing_in, wrap
from src.en.screen import centre_of, in_region, text_in_region

logger = Logger.get_logger(__name__)

# The four Desire factions, spelled as the client spells them. Survival is event-only - it cannot be bought.
FACTIONS = ("Claim", "Inquiry", "Control", "Survival")
# A card stops at level three, and its points total is its level. A tag claiming more than that is a reading
# that ran into the effect text, not a card.
MAX_LEVEL = 3
# One faction and the points beside it. The number is absent at a single point.
TAGGED = re.compile(rf"({'|'.join(FACTIONS)})\s*(\d*)", re.I)
# What a tag may contain besides its faction names: the points, and the brackets and slash the client draws.
# Anything else means the reading has run into the effect text and cannot be trusted.
DECORATION = re.compile(r"[\s\[\]()/|,.:0-9]*")

# The setting naming the faction to chase. Added fork-side, so it needs no upstream change and no migration.
FACTION_KEY = "Desire Faction"
DEFAULT_FACTION = "Claim"
# The card list already used to rank a card reward, which ranks these too once the faction is settled.
CARD_PRIORITY = "卡牌奖励优先级"

# The prompt that names the Desire card screen. Matched in English: nothing in `ok_tasks/` looks for this
# screen, so there is no Chinese literal for the catalog to rewrite it into.
REWARD_TITLE = "desire card reward"
# The prompt on the screen where two Desire cards merge. That screen's title is "Card Reward" like any other,
# so the prompt is the only thing telling it apart from an ordinary card reward.
INHERIT_TITLE = "desire card to inherit"
# Where those prompts are drawn, as (x1, y1, x2, y2).
TITLE_REGION = (0.150, 0.020, 0.850, 0.250)
# Upstream's own confirm button, which goes live only once a card has been chosen.
CONFIRM_POINT = (0.921, 0.931)

# The Purchase Card screen runs through the same handler as the card assign screen, and taking a card there
# spends credits. Its title is what tells the two apart.
PURCHASE_TITLE = "购买卡牌"
# Where a Desire screen leaves the card it took, for the assign screen that hands the card over to read.
TAKEN = "_en_desire_taken"
# Names this change in the shared record of what a function already carries.
ASSIGN_TAG = "desire cards worth keeping"

# Where an assign screen row prints the level of the Desire card its combatant holds, as (x1, y1, x2, y2) offsets
# from the row's level tag centre. Measured off two captures: the tag at (863, 823), and OCR reading "Ly." or "LV."
# at (1228, 870) and the "2" beside it at (1254, 872). Stopped short of the deck count at (1356, 851).
LEVEL_OFFSETS = (0.170, 0.025, 0.235, 0.070)
# The level's digit, which OCR reads as a box of its own. A card stops at `MAX_LEVEL`.
LEVEL_DIGIT = re.compile(r"[1-3]")
# Upstream's probe for a row's "Unobtainable" caption, as an offset from the level tag centre, and the word it wants.
UNOBTAINABLE_OFFSET = (0.0615, -0.0795)
UNOBTAINABLE = "无法获得"
# Where upstream looks for the save-data combatant's avatar on the assign screen, as (x1, y1, x2, y2).
SAVE_DATA_REGION = (0.484, 0.169, 0.652, 0.858)
# The most off-faction points the save-data combatant may hold. Its save data is what the run keeps, so it is saved
# for the chased faction: one off-faction point still leaves room for the two that make a majority.
SAVE_DATA_OFF_FACTION = 1
# How close a probed point has to be to a full row's caption point to be that probe. Upstream does the same sums.
SAME_POINT = 1e-6
# The bottom band upstream reads its Refresh and Skip buttons from, as (x1, y1, x2, y2), and what they say.
BUTTON_REGION = (0.290, 0.878, 0.998, 0.997)
REFRESH = "刷新"
SKIP = "跳过"
# The refreshes left, printed as "3/3".
REFRESHES_LEFT = re.compile(r"(\d+)/\d+")

_patched = False


def tags_of(text):
    """Read the factions and points out of a card's Desire tag.

    Args:
        text: One OCR box's text, which may or may not be a tag.

    Returns:
        A dict of faction to points, empty when the reading is not a tag.
    """
    if not text:
        return {}
    # Everything the tag is allowed to be made of is stripped out; a tag leaves nothing behind.
    remainder = DECORATION.sub("", TAGGED.sub("", text))
    if remainder:
        return {}
    tags = {}
    for faction, points in TAGGED.findall(text):
        # The client spells the faction; the reader's casing is not worth carrying.
        name = next(known for known in FACTIONS if known.casefold() == faction.casefold())
        tags[name] = int(points) if points else 1
    if not tags or sum(tags.values()) > MAX_LEVEL:
        return {}
    return tags


def points_of(tags):
    """Total a tag's points, which is the card's level.

    Args:
        tags: The dict `tags_of` produced.

    Returns:
        The number of points, zero when there is no tag.
    """
    return sum(tags.values())


def tag_of(task, region):
    """Find a card's Desire tag among the readings inside its description.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        region: The card's description region, as `recognize_cards` reported it.

    Returns:
        A dict of faction to points, empty when the card carries no readable tag.
    """
    for box in getattr(task, "all_texts", None) or []:
        if not in_region(box, region, task.width, task.height):
            continue
        tags = tags_of(box.name)
        if tags:
            return tags
    return {}


def best(cards, target, priority):
    """Choose which of the offered cards to take.

    The faction comes first and the user's list second. A card's effect matters, but the faction is what the
    rest of the run compounds on: reaching three, five or seven points in one of them is worth more than any
    single card, and points spread across four factions are worth nothing at all.

    Args:
        cards: The offered cards, each carrying a `tags` dict.
        target: The faction being chased.
        priority: The user's card list, best first.

    Returns:
        The card to take, or None when nothing was offered.
    """
    if not cards:
        return None
    carrying = [card for card in cards if card["tags"].get(target)]
    if carrying:
        return max(carrying, key=lambda card: card["tags"][target])
    for wanted in priority:
        for card in cards:
            if wanted and card["name"] and (wanted in card["name"] or card["name"] in wanted):
                return card
    return cards[0]


def target_faction(task, utils):
    """Read the faction the run is chasing.

    Args:
        task: The running task.
        utils: The loaded `utils` module, for its config reader.

    Returns:
        One of `FACTIONS`.
    """
    chosen = utils._get_config_value(task, FACTION_KEY, DEFAULT_FACTION)
    return chosen if chosen in FACTIONS else DEFAULT_FACTION


def reward_handler(utils):
    """Build the handler for the Desire card screen.

    Args:
        utils: The loaded `utils` module.

    Returns:
        The handler.
    """
    # There is no Skip on this screen, so something has to be taken whatever the reader managed to see.
    return choosing_handler(
        utils,
        REWARD_TITLE,
        "欲望卡牌奖励页面",
        lambda task, cards: best(cards, target_faction(task, utils),
                                 utils._get_card_list(task, CARD_PRIORITY)),
        "handle_desire_reward",
    )


def keeper(cards, priority):
    """Choose which card carries a merge.

    Both cards end with the same faction points - the captured pair read `[ Control / Inquiry 2 ]` and
    `[ Inquiry 2 / Control ]` - so the faction outcome is already settled and the only question is which
    card's effect stays in the deck. That is what the user's own card list is for.

    Args:
        cards: The two offered cards, each carrying a `tags` dict.
        priority: The user's card list, best first.

    Returns:
        The card to keep, or None when nothing was offered.
    """
    if not cards:
        return None
    for wanted in priority:
        for card in cards:
            if wanted and card["name"] and (wanted in card["name"] or card["name"] in wanted):
                return card
    # Nothing to separate them on effect, so the more levelled card wins; `max` keeps the first on a tie.
    return max(cards, key=lambda card: points_of(card["tags"]))


def choosing_handler(utils, title, page, choose, name):
    """Build a handler for a Desire screen that picks one card and lets the confirm button do the rest.

    Both Desire screens work the same way: read the cards, tag them, pick one, and stand aside once the
    client's own Confirm goes live, which is how the screen says something is selected.

    Args:
        utils: The loaded `utils` module.
        title: The prompt naming the screen.
        page: What to call the screen in the recognizer's log.
        choose: Takes the tagged cards and returns the one to click.
        name: The `__name__` the handler should carry, since position is the priority scheme.

    Returns:
        The handler.
    """
    def handler(task):
        if text_in_region(task, title, TITLE_REGION) is None:
            return False
        confirm = utils.find_box_at_point(task, *CONFIRM_POINT)
        if confirm and utils.is_button_active(task, confirm):
            return False
        cards = utils.recognize_cards(task, page=page)
        for card in cards:
            card["tags"] = tag_of(task, card["description_region"])
        chosen = choose(task, cards)
        if chosen is None:
            return False
        logger.info(f"{name}: taking 「{chosen['name']}」 tagged {chosen['tags'] or 'nothing'}")
        # The card assign screen judges the faction again as it hands the card over, and would throw an
        # off-faction pick straight back out. Leaving the name here tells it the choice is already made.
        setattr(task, TAKEN, chosen["name"])
        utils._move_and_click(task, chosen["x"], chosen["y"])
        task.sleep(0.5)
        return True

    handler.__name__ = name
    return handler


def inherit_handler(utils):
    """Build the handler for the screen where two Desire cards merge.

    Args:
        utils: The loaded `utils` module.

    Returns:
        The handler.
    """
    return choosing_handler(
        utils,
        INHERIT_TITLE,
        "欲望卡牌继承页面",
        lambda task, cards: keeper(cards, utils._get_card_list(task, CARD_PRIORITY)),
        "handle_desire_inherit",
    )


def points_held(task, row):
    """Read the level of the Desire card an assign screen row's combatant already holds.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        row: The row's level tag, as `_find_member_level_tags` found it.

    Returns:
        The points the combatant already holds, zero when it holds no Desire card or the digit was not read.
    """
    x, y = centre_of(row, task.width, task.height)
    left, top, right, bottom = LEVEL_OFFSETS
    region = (x + left, y + top, x + right, y + bottom)
    return next((int(box.name.strip()) for box in task.all_texts
                 if LEVEL_DIGIT.fullmatch(box.name.strip()) and in_region(box, region, task.width, task.height)), 0)


def caption_point(task, row):
    """Give the point upstream probes for a row's "Unobtainable" caption.

    Args:
        task: The running task, for the screen's size.
        row: The row's level tag, as `_find_member_level_tags` found it.

    Returns:
        An `(x, y)` pair in screen fractions.
    """
    x, y = centre_of(row, task.width, task.height)
    return x + UNOBTAINABLE_OFFSET[0], y + UNOBTAINABLE_OFFSET[1]


def obtainable(task, find_box_at_point, row):
    """Report whether a row's combatant can take the card, the way upstream decides it.

    Args:
        task: The running task.
        find_box_at_point: Upstream's point reader.
        row: The row's level tag.

    Returns:
        False when the row carries the "Unobtainable" caption.
    """
    caption = find_box_at_point(task, *caption_point(task, row))
    return not (caption and UNOBTAINABLE in caption.name)


def reroll_or_skip(task, utils):
    """Press Refresh while any are left, and Skip once they run out.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        utils: The loaded `utils` module, for the client's own wording of Refresh.

    Returns:
        True when a button was pressed.
    """
    buttons = [box for box in task.all_texts if in_region(box, BUTTON_REGION, task.width, task.height)]
    left = next((int(found.group(1)) for box in buttons if (found := REFRESHES_LEFT.search(box.name))), 0)
    button = text_in_region(task, utils._get_game_text(task, REFRESH) if left else SKIP, BUTTON_REGION)
    if button is None:
        return False
    action = "rerolling" if left else "skipping"
    logger.info(f"every combatant able to take the card already holds {MAX_LEVEL} Desire points, so {action} with {left} refresh(es) left")
    task.click_box(button)
    return True


def purchasing(task):
    """Report whether the screen showing is the one that spends credits.

    The Purchase Card screen runs through the same handler as the card assign screen, so a card kept there
    would be bought rather than granted. Matched anywhere on screen rather than in upstream's own title band,
    because a band copied out of vendored code drifts silently and this is the check standing between the
    run and its credits.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        True when the card in front of the handler is for sale.
    """
    return any(PURCHASE_TITLE in box.name for box in getattr(task, "all_texts", None) or [])


def keeping_desire_cards(handler, utils):
    """Wrap `handle_card_assign` so a granted Desire card is kept instead of skipped.

    That handler judges the card in front of it on one thing: whether its name is on the user's reward
    priority list. A Desire card's name never is - the card is named for its effect, and what makes it worth
    keeping is the faction tag printed underneath. So the run reaches the screen, misses, and presses Skip,
    throwing away points an event had already paid for.

    Rather than re-deciding the screen, the card's name is offered to upstream's own ladder as though the
    list had asked for it. Everything after that is upstream's, including its preference for handing the card
    to the save-data combatant.

    Every faction earns this, not only the one being chased. The aim is all three combatants at three points, and a
    real run chasing Claim skipped a Control card with nothing else on offer. The chased faction is favoured where
    there is a choice to make - the event options and the Desire screens - not here, where the only other answer is Skip.
    The one exception is the save-data combatant, whose slots are kept for the chased faction.

    The exception is a card a Desire screen already chose, which is kept whatever it carries. That screen has
    no Skip, so something had to be taken; re-judging the faction here only throws the choice away and leaves
    the run with nothing.

    A kept card is never handed to a combatant already holding `MAX_LEVEL` points.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module whose card, list, row and point readers the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        recognize_cards, read_list = utils.recognize_cards, utils._get_card_list
        find_rows, find_box_at_point = utils._find_member_level_tags, utils.find_box_at_point
        read, wanted, off_faction, card_points, stalled, passed_over = False, None, False, 0, False, []

        def recognised(task_, *args, **kwargs):
            # The first read is the granted card. The handler has to read a card before it can judge one, and
            # it reads no other, so taking the first is steadier than matching the page label it passes -
            # that label only reaches a log, and a rebase renaming it would quietly bring the bug back.
            nonlocal read, wanted, off_faction, card_points
            cards = recognize_cards(task_, *args, **kwargs)
            if read or not cards:
                return cards
            read = True
            card = cards[0]
            chosen = getattr(task_, TAKEN, None) == card["name"]
            # Reasserted rather than consumed, because this screen shows for as long as it takes to answer and
            # the handler runs once a second throughout. A different card means the pick was already handed
            # over, so the name goes.
            setattr(task_, TAKEN, card["name"] if chosen else None)
            tags = tag_of(task_, card["description_region"])
            if not (chosen or tags):
                return cards
            because = "was chosen on the Desire screen" if chosen else f"carries {tags}"
            if purchasing(task_):
                logger.info(f"「{card['name']}」{because}, but it is for sale, so it is left alone")
            else:
                wanted, card_points = card["name"], points_of(tags)
                # A chosen card with no readable tag is not called off-faction, since nothing says it is.
                off_faction = bool(tags) and not tags.get(target_faction(task_, utils))
                logger.info(f"「{card['name']}」{because}, so it is kept rather than skipped")
            return cards

        # `_get_card_list` rather than the reader under it: upstream reaches the list through this in both
        # places it reads it, and it has already coerced whatever the config held into a list.
        def reading(task_, key):
            listed = read_list(task_, key)
            return [wanted, *listed] if key == CARD_PRIORITY and wanted else listed

        def rows_with_room(task_, *args, **kwargs):
            nonlocal stalled
            rows = find_rows(task_, *args, **kwargs)
            if not wanted:
                return rows
            held = {id(row): points_held(task_, row) for row in rows if obtainable(task_, find_box_at_point, row)}
            able = [row for row in rows if id(row) in held]
            blocked = [row for row in able if held[id(row)] >= MAX_LEVEL]
            if blocked:
                logger.info(f"「{wanted}」 is not handed to a combatant already holding {MAX_LEVEL} Desire points")
            saver = utils._find_target_member_index(task_, rows, SAVE_DATA_REGION) if off_faction else None
            if saver is not None and rows[saver] in able and rows[saver] not in blocked:
                others = [row for row in able if row is not rows[saver] and row not in blocked]
                if others or held[id(rows[saver])] + card_points > SAVE_DATA_OFF_FACTION:
                    logger.info(f"「{wanted}」 is off the chased faction, so it is kept off the save-data combatant")
                    blocked.append(rows[saver])
            passed_over.extend(caption_point(task_, row) for row in blocked)
            if blocked and len(blocked) == len(able):
                # Upstream would skip with refreshes still left. Handed no rows, it answers False and presses nothing.
                stalled = True
                return []
            return rows

        def probed(task_, x, y):
            # A passed-over row's caption probe reads "Unobtainable", so upstream's own exclusion skips the row.
            if any(abs(x - fx) < SAME_POINT and abs(y - fy) < SAME_POINT for fx, fy in passed_over):
                return SimpleNamespace(name=UNOBTAINABLE)
            return find_box_at_point(task_, x, y)

        with standing_in(utils, recognize_cards=recognised, _get_card_list=reading,
                         _find_member_level_tags=rows_with_room, find_box_at_point=probed):
            handled = handler(task)
        return reroll_or_skip(task, utils) if stalled else handled

    return wrapped


def install(utils):
    """Claim every screen a Desire card can arrive on.

    The two Desire screens are claimed ahead of the handler that would otherwise take them. The card assign
    screen stays upstream's, wrapped only so a granted Desire card is not thrown away.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    # Ahead of the confirm button: its own Confirm is greyed until a card is chosen, so the confirm handler
    # spinning on it is what stalled the run.
    insert_before("handle_confirm", reward_handler(utils))
    # Ahead of the ordinary card reward: both screens are titled "Card Reward", and upstream's handler finds
    # no priority match on this one and presses Skip, throwing the merge away.
    insert_before("handle_card_reward", inherit_handler(utils))
    # The screen an event's Desire card actually lands on, which skips anything the user's list did not name.
    wrap(utils, "handle_card_assign", lambda handler: keeping_desire_cards(handler, utils), ASSIGN_TAG)


def apply():
    """Choose Desire cards deliberately instead of letting the stuck-screen fallback pick at random."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
