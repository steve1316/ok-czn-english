"""Fill an empty shop or reward priority list with what is worth taking from the screen.

A list you configured is used unchanged.
"""

from ok import Logger

from src.en import quality
from src.en.handlers import loaded, register, replace
from src.en.screen import COMBATANT_NAME_POINTS

logger = Logger.get_logger(__name__)

# The card list the shop and the Chaos reward screen both read, and the one Sortie's reward screen reads.
CARD_KEY = "卡牌奖励优先级"
SORTIE_CARD_KEY = "获得卡牌优先级"
# The three equipment slots, in the order the handlers number them.
EQUIPMENT_KEYS = {"装备1号位优先级": 0, "装备2号位优先级": 1, "装备3号位优先级": 2}

TEAM = "_en_team"

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
    names = []
    for x, y in COMBATANT_NAME_POINTS:
        box = utils.find_box_at_point(task, x, y)
        if box and box.name.strip():
            names.append(box.name.strip())
    classes = quality.team_classes(names)
    if classes:
        setattr(task, TEAM, classes)
        logger.info(f"team is {names}, covering {quality.named(classes)}")
    else:
        logger.info(f"team {names} matched no known combatant, so cards will not be class filtered")


def team_of(task):
    """Read back the classes captured at the start of the run.

    Args:
        task: The running task.

    Returns:
        The team's classes, empty when the Combatants screen has not been read yet.
    """
    return getattr(task, TEAM, set())


def on_screen(task):
    """List the text the reader currently sees.

    Args:
        task: The running task.

    Returns:
        Every box's text, which is what the item names are graded from.
    """
    return [box.name for box in (task.all_texts or []) if box.name]


def generated_list(task, key):
    """Build the priority list for a setting the user left empty.

    Args:
        task: The running task.
        key: The config key being read.

    Returns:
        The names worth taking, best first, or None when this key is not one we fill in.
    """
    # Only what is on screen. Offering every Legend and Unique name would give upstream's plain-containment
    # matcher 625 chances to pair a short name with a longer one and buy the wrong thing.
    names = on_screen(task)
    classes = team_of(task)
    if key in (CARD_KEY, SORTIE_CARD_KEY):
        return quality.worth_taking(names, classes)
    slot = EQUIPMENT_KEYS.get(key)
    if slot is None:
        return None
    return [name for name in quality.worth_taking(names, classes, cards=False)
            if quality.slot_of(name) == slot]


def filling_in(original, task_module):
    """Wrap a config reader so an empty priority list is filled in from what is on screen.

    Args:
        original: The module's own `_get_config_value`.
        task_module: The module whose copy of it is being replaced, named for the log.

    Returns:
        The replacement reader.
    """
    def patched(task, key, default):
        configured = original(task, key, default)
        if configured:
            return configured
        generated = generated_list(task, key)
        if not generated:
            return configured
        logger.info(f"{task_module}: {key} is empty, offering {generated}")
        return generated

    return patched


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
    def wrapped(task):
        originals = [(module, module._get_config_value) for module in modules]
        for module, original in originals:
            module._get_config_value = filling_in(original, module.__name__)
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

        for name in ("handle_shop", "handle_card_reward"):
            handler = getattr(utils, name, None)
            if handler is not None:
                replace(name, with_generated_lists(handler, [utils]))

        if utils_sortie is not None and hasattr(utils_sortie, "handle_get_card"):
            # Sortie imported its own reference to the reader, so that copy is the one it resolves through.
            replace("handle_get_card",
                    with_generated_lists(utils_sortie.handle_get_card, [utils_sortie, utils]))

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
