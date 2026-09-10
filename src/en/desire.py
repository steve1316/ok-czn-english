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
"""

import re

from ok import Logger

from src.en.handlers import insert_before, loaded, register
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

_patched = False


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


def install(utils):
    """Claim both Desire screens, each ahead of the handler that would otherwise take it.

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


def apply():
    """Choose Desire cards deliberately instead of letting the stuck-screen fallback pick at random."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
