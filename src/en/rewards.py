"""Fill an empty shop or reward priority list with what is worth taking from the screen.

A list you configured is used unchanged. This also owns the run-time half of the dashboard's Combatants row,
because reading the team off the screen is what fills it - `src/en/dashboard.py` owns the row itself, its name,
its place in the table and what it says before it has been read.
"""

from ok import Logger

from src.en import cards, quality
from src.en.battle import PARTY
from src.en.dashboard import COMBATANTS, UNREAD
from src.en.handlers import insert_before, loaded, register, replace
from src.en.navigation import team_pending
from src.en.overrides import FARMED_COMBATANT
from src.en.screen import combatant_names, same_line

logger = Logger.get_logger(__name__)

# The card list the shop and the Chaos reward screen both read, and the one Sortie's reward screen reads.
CARD_KEY = "卡牌奖励优先级"
SORTIE_CARD_KEY = "获得卡牌优先级"
# The three equipment slots, in the order the handlers number them.
EQUIPMENT_KEYS = {"装备1号位优先级": 0, "装备2号位优先级": 1, "装备3号位优先级": 2}

# The handlers in `utils` that judge something against a priority list, and so need one filled in when the
# user left it empty. `handle_card_assign` belongs here because it is the screen that confirms a purchase the
# shop's own handler already decided on: without the same list, the shop buys and the purchase screen
# cancels, forever.
FILLED_IN = ("handle_shop", "handle_card_reward", "handle_card_assign")
# The reward screens, Chaos's and Sortie's, where a card costs nothing. The shop shares Chaos's list, so the
# handler reading it is what tells them apart.
FREE = ("handle_card_reward", "handle_get_card")

# Upstream's own check for Sortie's Obtain Card screen: its title, and the point it reads it at.
OBTAIN_TITLE = "获得卡牌"
OBTAIN_TITLE_AT = (0.502, 0.128)

TEAM = "_en_team"

# The handler that reads the team. It is the scope as well as the anchor: exactly the modes that read a team
# register it, so anchoring on it keeps the placeholder row off Story, which never reads one.
ARCHIVE_ANCHOR = "handle_archive_target_member"

_patched = False


def remember_team(task, utils):
    """Read the team off the Combatants screen and keep it for the rest of the run.

    The bot already visits this screen once per run to capture the save-target's portrait, and already reads
    all three names to find them - it just throws the other two away. Reading them again here costs nothing,
    because the OCR pass the handler made is still the current one when it returns.

    Args:
        task: The running task.
        utils: The loaded `utils` module.
    """
    names = [name for name in combatant_names(task, utils) if name]
    if names:
        show_team(task, names)
    else:
        logger.info("the Combatants screen showed no names, so cards will not be class filtered")


def show_team(task, names):
    """Show the team in the Combatants row and keep it for the card picker and the reward screens.

    Args:
        task: The running task.
        names: The whole team, as read off the Combatants screen or grown by a draft.
    """
    task.info_set(COMBATANTS, ", ".join(names))
    party = frozenset(filter(None, map(quality.COMBATANT_INDEX.look_up, names)))
    if party:
        # Read off a screen, so it replaces whatever the hand taught the card picker before.
        setattr(task, PARTY, party)
    classes = quality.team_classes(names)
    if classes:
        setattr(task, TEAM, classes)
        logger.info(f"team is {names}, covering {quality.named(classes)}")
    else:
        logger.info(f"team {names} matched no known combatant, so cards will not be class filtered")


def hold_the_combatants_row(task):
    """Keep the team's row in the table from the first frame of a run, before the screen has been read.

    Upstream empties the table on Start, so the row would otherwise be missing until `remember_team` fills it
    - which after the idle table has drawn it reads as the row vanishing and coming back minutes later.

    Args:
        task: The running task.

    Returns:
        False always. This claims no frame, it only seeds a row that has nothing to show yet.
    """
    if COMBATANTS not in task.info:
        task.info_set(COMBATANTS, UNREAD)
    return False


def team_of(task):
    """Read back the classes captured at the start of the run.

    Args:
        task: The running task.

    Returns:
        The team's classes, empty when the Combatants screen has not been read yet.
    """
    return getattr(task, TEAM, set())


def party_cards(names, party):
    """Pick out the cards on screen that belong to someone on the team.

    Args:
        names: Candidate names as read off the screen.
        party: Names of the combatants on the team, from `battle.PARTY`.

    Returns:
        The canonical names, in screen order, each appearing once.
    """
    found = []
    for name in names:
        card = quality.CARD_INDEX.look_up(name)
        if card and cards.owner(card) in party and card not in found:
            found.append(card)
    return found


def held_help(names, classes):
    """Pick out the cards on screen that help just by being held, such as Unknown: Mutant Sample, which are worth having at any grade.

    Args:
        names: Candidate names as read off the screen.
        classes: The team's classes, used to skip cards nobody could hold.

    Returns:
        The canonical names, in screen order, each appearing once.
    """
    found = []
    for name in names:
        card = quality.CARD_INDEX.look_up(name)
        if card and cards.helps_held(card) and quality.usable_by(card, classes) and card not in found:
            found.append(card)
    return found


def upgrades(names, classes):
    """Pick out the Upgrade cards on screen, which are played once and then keep working for the rest of the fight.

    Args:
        names: Candidate names as read off the screen.
        classes: The team's classes, used to skip cards nobody could hold.

    Returns:
        The canonical names, in screen order, each appearing once.
    """
    found = []
    for name in names:
        card = quality.CARD_INDEX.look_up(name)
        if card and cards.category(card) == cards.SETUP_CATEGORY and quality.usable_by(card, classes) and card not in found:
            found.append(card)
    return found


def stacked(upper, lower):
    """Say whether two boxes are consecutive lines of one wrapped caption.

    Args:
        upper: The box that would be the first line.
        lower: The box that would be the second.

    Returns:
        True when `lower` is the next line down, starting within one line height of `upper`, and the two share a centre.
    """
    within_a_line = lower.y - (upper.y + upper.height) < upper.height
    shared_centre = abs((upper.x + upper.width / 2) - (lower.x + lower.width / 2)) < max(upper.width, lower.width) / 2
    return not same_line(upper, lower) and within_a_line and shared_centre


def on_screen(task):
    """List the text the reader currently sees, reading a wrapped name whole.

    The two halves of a wrapped name come back as separate boxes, and a half can be another card's whole name.

    Args:
        task: The running task.

    Returns:
        Every box's text, which is what the item names are graded from.
    """
    boxes = [box for box in (task.all_texts or []) if box.name]
    names = {id(box): box.name for box in boxes}
    for upper in boxes:
        for lower in boxes:
            # A line already taken as the second half of a name cannot start another.
            if lower is upper or id(upper) not in names or not stacked(upper, lower):
                continue
            joined = f"{upper.name} {lower.name}"
            if quality.CARD_INDEX.look_up(joined) or quality.EQUIPMENT_INDEX.look_up(joined):
                names[id(upper)] = joined
                names.pop(id(lower), None)
    return list(names.values())


def generated_list(task, key, farmed="", free=False):
    """Build the priority list for a setting the user left empty.

    Args:
        task: The running task.
        key: The config key being read.
        farmed: The combatant whose save data the run is farming, who is the one equipment is bought for.
            Empty leaves equipment in the order rarity alone puts it.
        free: True on a reward screen, where a team member's own card is worth having at any grade.

    Returns:
        The names worth taking, best first, or None when this key is not one we fill in.
    """
    slot = EQUIPMENT_KEYS.get(key)
    card_list = key in (CARD_KEY, SORTIE_CARD_KEY)
    if slot is None and not card_list:
        return None
    # Only what is on screen. Offering every Legend and Unique name would give upstream's plain-containment
    # matcher 625 chances to pair a short name with a longer one and buy the wrong thing.
    names = on_screen(task)
    classes = team_of(task)
    if card_list:
        taken = quality.worth_taking(names, classes)
        if free:
            taken += [card for card in held_help(names, classes) + party_cards(names, getattr(task, PARTY, frozenset())) if card not in taken]
            # A free Upgrade such as Mutation: Iron Wall still beats skipping the reward.
            taken = taken or upgrades(names, classes)
        # A card the deck already holds adds less than one it lacks, so it goes after every card the deck lacks, at any grade.
        return sorted(taken, key=lambda card: card in cards.DECK)
    # Ordered by who is going to wear it. Rarity still decides, so this only separates pieces that were
    # otherwise going to be picked between on their names.
    return [name for name in quality.worth_taking(names, classes, cards=False, suited_to=farmed)
            if quality.slot_of(name) == slot]


def filling_in(original, task_module, free=False):
    """Wrap a config reader so an empty priority list is filled in from what is on screen.

    Args:
        original: The module's own `_get_config_value`.
        task_module: The module whose copy of it is being replaced, named for the log.
        free: True when the handler reading it is a reward screen, from `FREE`.

    Returns:
        The replacement reader.
    """
    def patched(task, key, default):
        configured = original(task, key, default)
        if configured:
            return configured
        # Through `original` rather than the module attribute, which is this function for the length of the
        # call - asking through that would come straight back here.
        generated = generated_list(task, key, original(task, FARMED_COMBATANT, ""), free)
        if not generated:
            return configured
        logger.info(f"{task_module}: {key} is empty, offering {generated}")
        return generated

    return patched


def after_the_team(handler, utils_sortie):
    """Hold Sortie's Obtain Card pick while the run's first team read still has tries left, so the pick knows the team and the deck.

    A run started on this screen taps for the team as the game window comes to the front, which loses the tap, and upstream picked in the
    wait before the retry.

    Args:
        handler: Upstream's `handle_get_card`.
        utils_sortie: The Sortie module, whose `find_box_at_point` reads the screen title.

    Returns:
        The wrapped handler, under the original's name.
    """
    def handle_get_card(task):
        title = utils_sortie.find_box_at_point(task, *OBTAIN_TITLE_AT)
        if title and title.name == OBTAIN_TITLE and team_pending(task):
            logger.debug("Obtain Card waits for the team and the deck to be read")
            task.sleep(1)
            return True
        return handler(task)

    handle_get_card.__name__ = handler.__name__
    return handle_get_card


def with_generated_lists(handler, modules):
    """Run a handler with the empty priority lists filled in for the length of the call.

    Scoping it to the call is what keeps this out of the event handler, which prepends the same equipment
    lists when it ranks options - filling them in there would make every event prefer an equipment option.

    Args:
        handler: The upstream handler to wrap.
        modules: The modules whose `_get_config_value` the handler resolves through.

    Returns:
        The wrapped handler.
    """
    free = handler.__name__ in FREE

    def wrapped(task):
        originals = [(module, module._get_config_value) for module in modules]
        for module, original in originals:
            module._get_config_value = filling_in(original, module.__name__, free)
        try:
            return handler(task)
        finally:
            for module, original in originals:
                module._get_config_value = original

    # A distinct name is what makes installing twice a no-op: `replace` matches by name, so once the list
    # holds this, nothing named after the original is left for a later install to wrap again.
    wrapped.__name__ = f"{handler.__name__}_filling_empty_lists"
    return wrapped


def apply():
    """Fill in the empty reward lists, and remember who is on the team."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        utils_chaos = loaded("utils_chaos")
        utils_sortie = loaded("utils_sortie")
        if utils is None:
            return

        # Before the replace at the foot of this function, which stands the anchor down under a new name.
        # A later load finds the row handler already registered and leaves the list alone.
        insert_before(ARCHIVE_ANCHOR, hold_the_combatants_row)

        for name in FILLED_IN:
            handler = getattr(utils, name, None)
            if handler is not None:
                replace(name, with_generated_lists(handler, [utils]))

        if utils_sortie is not None and hasattr(utils_sortie, "handle_get_card"):
            # Sortie imported its own reference to the reader, so that copy is the one it resolves through.
            replace("handle_get_card",
                    with_generated_lists(after_the_team(utils_sortie.handle_get_card, utils_sortie), [utils_sortie, utils]))

        if utils_chaos is not None and hasattr(utils_chaos, "handle_archive_target_member"):
            original_archive = utils_chaos.handle_archive_target_member

            def patched_archive_target_member(task):
                handled = original_archive(task)
                if handled:
                    remember_team(task, utils)
                return handled

            replace("handle_archive_target_member", patched_archive_target_member)

    register(install)
    _patched = True
