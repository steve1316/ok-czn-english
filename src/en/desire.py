"""Read and steer Season 4's Desire cards.

Season 4 gives every combatant one Desire card. Obtaining another of the same faction levels the card up;
obtaining a different one opens an inherit screen where the two merge into a single card carrying both tags.
Each card caps at level three, so a team of three carries nine points, and reaching three, five or seven
points in one faction unlocks a team-wide bonus. Concentrating on one faction is therefore worth much more
than spreading across four, which is what the target-faction setting is for.

**The tag is the whole state.** The client prints it on the card itself: `[ Inquiry ]` at level one,
`[ Inquiry 2 ]` at level two, `[ Control / Inquiry 2 ]` once two factions have merged. Faction and points are
both there, and the points total is the card's level. Nothing has to be remembered between frames, which
matters because a run can be resumed, or the bot restarted, part way through a node.

**Reading it is the hard part.** The tag shares a region with the effect text below it, and the reader loses
brackets, drops spaces and sometimes glues the tag straight onto the sentence under it - one captured frame
produced `Control200% Damage to all...`. So the shape is tested rather than searched: a reading only counts as
a tag when everything in it is a faction name, a number, or bracket-and-slash punctuation, and when its points
add up to a level a card can actually reach. That turns away a mangled tag, and it turns away a sentence that
happens to contain the word Control. Turning away a real tag costs one frame of a screen the bot re-reads
every second; acting on a misread one would steer every card pick for the rest of the run.

**Most Desire cards arrive on a screen that is not a Desire screen.** An event that grants one drops the run
onto the ordinary card assign screen, which decides on the user's reward priority list alone. A Desire card
is named for its effect, so the list never names it, and the run pressed Skip on every one - twice in the
four minutes of a real run. That screen is claimed here too, but only to the extent of telling upstream the
card is worth keeping.

**The Desire screen and the assign screen are one decision, not two.** Taking a card on the Desire screen
drops the run onto the assign screen to hand it over, and judging the faction a second time there threw away
what the first screen had just chosen - a real run picked `Knowledge Addiction` off three cards none of which
were the faction being chased, then skipped it four seconds later. So a Desire screen leaves the name of what
it took on the task, and the assign screen honours it. The purchase guard still outranks that: nothing here
ever spends credits.
"""

import re

from ok import Logger

from src.en.handlers import insert_before, loaded, register, standing_in, wrap
from src.en.screen import in_region, text_in_region

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

    Only the faction being chased earns this. Handed to a combatant carrying nothing yet, an off-faction
    card takes one of the team's three Desire slots outright, costing up to three points against a bonus
    that wants seven of nine. Levels run out well before the cards do.

    The exception is a card a Desire screen already chose, which is kept whatever it carries. That screen has
    no Skip, so something had to be taken; re-judging the faction here only throws the choice away and leaves
    the run with nothing.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        utils: The module whose `recognize_cards` and card list reader the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        recognize_cards, read_list = utils.recognize_cards, utils._get_card_list
        read, wanted = False, None

        def recognised(task_, *args, **kwargs):
            # The first read is the granted card. The handler has to read a card before it can judge one, and
            # it reads no other, so taking the first is steadier than matching the page label it passes -
            # that label only reaches a log, and a rebase renaming it would quietly bring the bug back.
            nonlocal read, wanted
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
            target = target_faction(task_, utils)
            because = "was chosen on the Desire screen" if chosen else f"carries {target}"
            if not (chosen or tags.get(target)):
                logger.info(f"「{card['name']}」carries {tags} rather than {target}, so it is left to be skipped")
            elif purchasing(task_):
                logger.info(f"「{card['name']}」{because}, but it is for sale, so it is left alone")
            else:
                wanted = card["name"]
                logger.info(f"「{card['name']}」{because}, so it is kept rather than skipped")
            return cards

        # `_get_card_list` rather than the reader under it: upstream reaches the list through this in both
        # places it reads it, and it has already coerced whatever the config held into a list.
        def reading(task_, key):
            listed = read_list(task_, key)
            return [wanted, *listed] if key == CARD_PRIORITY and wanted else listed

        with standing_in(utils, recognize_cards=recognised, _get_card_list=reading):
            return handler(task)

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
