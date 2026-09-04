"""Re-shape the mode settings for the Global (English) client.

Upstream's task files ship one Chinese player's build as defaults and ask the user to type entity names by
hand. On the Global client those Chinese names can never match what the OCR reads, so they are replaced with
English defaults and, wherever the value set is knowable, with pick-from-a-list widgets built from the game's
own localization table.

Everything here is applied by wrapping `BaseTask.post_init`, which the framework calls once per task after it is
constructed. That keeps `ok_tasks/ChaosMode.py` and `ok_tasks/SortieMode.py` byte-identical to upstream, so a
merge never conflicts in them.

Two rules decide whether a setting can become a pick-list:

- The value must be compared against **OCR text**. Card, equipment and combatant names are, so those become
  lists of English names. Route Priority is not - its values are internal labels produced from template
  feature names (`enemy_in_map` -> `小怪`), so they stay Chinese and are only translated for display.
- The match must be on a **whole name**. Epiphany Priority, the Persona settings and Farm Starting Card are
  matched as subsequences of `name + description`, which is how a user targets an effect rather than a card.
  Restricting those to full card names would take that away, so they stay free text.
"""

import re

from ok import Logger

from src.en.game_data import CARDS, COMBATANTS, EQUIPMENT

logger = Logger.get_logger(__name__)

CJK = re.compile("[" + chr(0x4E00) + "-" + chr(0x9FFF) + "]")

# Route Priority values are internal labels, never OCR text, so they must stay exactly as upstream writes
# them. `ok.po` translates them for display, and ModifyListDialog stores the canonical value.
ROUTE_NODES = ["休息", "事件", "小怪", "精英"]
# Game Language stays a real setting for the Chinese clients. English behaves like Simplified Chinese, since
# `_get_game_text` falls back to the untranslated literal when a language has no map file.
GAME_LANGUAGES = ["English", "简体中文", "繁体中文"]
DEFAULT_SAVE_DATA_COMBATANT = "Heidemarie"

# A list setting the user picks from, keyed by config name -> the roster it draws on.
LIST_OPTIONS = {
    "移除卡牌列表": CARDS,
    "复制卡牌列表": CARDS,
    "闪光卡牌列表": CARDS,
    "需要冥想的卡牌": CARDS,
    "卡牌奖励优先级": CARDS,
    "获得卡牌优先级": CARDS,
    "丢弃卡牌优先级": CARDS,
    "出牌优先级": CARDS,
    "装备1号位优先级": EQUIPMENT,
    "装备2号位优先级": EQUIPMENT,
    "装备3号位优先级": EQUIPMENT,
    "出战主战员优先级": COMBATANTS,
    "主战员优先级": COMBATANTS,
    "拉黑主战员": COMBATANTS,
    "路线优先级": ROUTE_NODES,
}

# Free-text settings whose Chinese default cannot carry over. Cleared so the user fills them from what the
# client actually shows, rather than inheriting a value that can never match.
CLEARED_TEXT = ["指定面具卡牌", "面具卡牌刻印", "刷初始卡牌"]
CLEARED_LISTS = ["闪光优先级", "任务优先级", "拉黑任务"]

# Settings this module owns, and so may reset when their saved value is stale.
MANAGED_KEYS = set(LIST_OPTIONS) | set(CLEARED_TEXT) | set(CLEARED_LISTS) | {"刷存档主战员"}
# Route Priority is meant to hold Chinese, and Chinese is a real choice for Game Language.
EXEMPT_FROM_RESET = {"路线优先级", "游戏语言"}

# Help text, in the client's own wording.
DESCRIPTIONS = {
    "游戏语言": "Leave this on English for the Global client. The Chinese clients need Simplified or Traditional.",
    "路线优先级": "Which map node to head for first. Safe Zones restore health, Unidentified Areas run an event.",
    "移除卡牌列表": "Cards to delete from the deck whenever a removal is offered.",
    "复制卡牌列表": "Cards to duplicate whenever a copy is offered.",
    "闪光卡牌列表": "Cards to spend an Epiphany on.",
    "闪光优先级": "Epiphany targets, matched loosely against a card's name and its description, so a few keywords are enough. Order matters.",
    "需要冥想的卡牌": "Cards worth meditating on once Credits allow.",
    "卡牌奖励优先级": "Preferred cards when a reward offers a choice.",
    "获得卡牌优先级": "Preferred cards when the run offers a card to obtain.",
    "丢弃卡牌优先级": "Cards to throw away first when the run asks you to discard.",
    "出牌优先级": "Order to play cards in battle. Needs shortcut key display turned on in the game's settings.",
    "装备1号位优先级": "Preferred equipment for the first slot, best first.",
    "装备2号位优先级": "Preferred equipment for the second slot, best first.",
    "装备3号位优先级": "Preferred equipment for the third slot, best first.",
    "出战主战员优先级": "Combatants to deploy, in order of preference.",
    "主战员优先级": "Combatants to pick when the run offers a choice.",
    "拉黑主战员": "Combatants to never pick.",
    "刷存档主战员": "The combatant whose save data is farmed.",
    "指定面具卡牌": "The Persona Card to hold out for, matched against its name and description.",
    "面具卡牌刻印": "The Engraving to hold out for on that Persona Card.",
    "刷初始卡牌": "Reroll the starting card until this one appears. Cannot be combined with Farm Gaps.",
    "任务优先级": "Preferred options inside an Unidentified Area, matched against the option text.",
    "拉黑任务": "Unidentified Area options to never take.",
    "存储数据价值大于等于多少层级": "Only keep a run whose Save Data Value reaches this tier.",
    "保留大于多少TB的存档": "Only keep save data above this size.",
    "优先使用金币治疗": "Pay Credits at the Epione Center instead of spending a travel voucher.",
    "进入商店": "Stop at the Dellang Shop when a Safe Zone offers one.",
    "优先移除基础牌": "Clear basic cards out of the deck before anything else.",
    "只打第一层": "Leave after the first floor instead of running the whole map.",
}


def _apply_list_options(task):
    """Turn the entity settings into pick-from-a-list widgets.

    Args:
        task: The task being configured.
    """
    for key, options in LIST_OPTIONS.items():
        if key not in task.default_config:
            continue
        task.config_type[key] = {"type": "drop_down", "options_available": list(options)}
        if key != "路线优先级":
            # Upstream's defaults are Chinese card and combatant names that cannot match English OCR. The
            # restricted list would strip them on first launch anyway, so start empty and let the user pick.
            task.default_config[key] = []


def _apply_cleared_defaults(task):
    """Empty the free-text settings whose Chinese defaults cannot carry over.

    These stay free text because they are matched as subsequences of a card's name and description.

    Args:
        task: The task being configured.
    """
    for key in CLEARED_TEXT:
        if key in task.default_config:
            task.default_config[key] = ""
            # Pin the widget: the factory picks by default length, and a translated string over 16 characters
            # would silently become a multi-line text box.
            task.config_type[key] = {"type": "line_edit"}
    for key in CLEARED_LISTS:
        if key in task.default_config:
            task.default_config[key] = []


def _apply_language(task):
    """Offer English as the game language and make it the default.

    Args:
        task: The task being configured.
    """
    if "游戏语言" not in task.default_config:
        return
    task.config_type["游戏语言"] = {"type": "drop_down", "options": list(GAME_LANGUAGES)}
    task.default_config["游戏语言"] = GAME_LANGUAGES[0]


def _apply_combatant_choice(task):
    """Make the save-data combatant a dropdown rather than a typed name.

    Args:
        task: The task being configured.
    """
    if "刷存档主战员" not in task.default_config:
        return
    task.config_type["刷存档主战员"] = {"type": "drop_down", "options": list(COMBATANTS)}
    task.default_config["刷存档主战员"] = DEFAULT_SAVE_DATA_COMBATANT


def _has_chinese(value):
    """Report whether a saved setting still holds Chinese text.

    Args:
        value: A setting value, either a string or a list of them.

    Returns:
        True when any part of it contains a CJK character.
    """
    parts = value if isinstance(value, (list, tuple)) else [value]
    return any(isinstance(part, str) and CJK.search(part) for part in parts)


def _reset_stale_values(task):
    """Clear saved Chinese values that can never match on the Global client.

    Changing `default_config` only affects a fresh install: a value already written to `configs/` wins over
    it. The restricted lists drop what they cannot offer, but the free-text settings would otherwise keep a
    Chinese card name forever, and a combatant dropdown would sit blank because its saved name is not on the
    English roster.

    Route Priority is exempt because its values are supposed to be Chinese, and Game Language because Chinese
    is a real choice there.

    Args:
        task: The task being configured.
    """
    config = getattr(task, "config", None)
    if config is None:
        return
    for key, default in task.default_config.items():
        if key in EXEMPT_FROM_RESET or key not in MANAGED_KEYS:
            continue
        try:
            current = config.get(key)
        except Exception:
            continue
        if current is not None and _has_chinese(current):
            config[key] = default() if callable(default) else (list(default) if isinstance(default, list) else default)
            logger.info(f"reset '{key}' - its saved value was Chinese and cannot match the Global client")


def apply_to(task):
    """Re-shape one task's settings for the Global client.

    Args:
        task: The task being configured.
    """
    if not hasattr(task, "default_config") or not hasattr(task, "config_type"):
        return
    _apply_language(task)
    _apply_list_options(task)
    _apply_cleared_defaults(task)
    _apply_combatant_choice(task)
    _reset_stale_values(task)

    for key, text in DESCRIPTIONS.items():
        if key in task.default_config:
            task.config_description[key] = text

    # Upstream leaves ok-script's scaffold placeholder here, a bare link to the framework repo. The button
    # hides itself when this is empty.
    task.instructions = None
    logger.info(f"applied Global client settings to {task.__class__.__name__}")


def apply():
    """Wrap `BaseTask.post_init` so every task is re-shaped as the framework builds it.

    Hooking the base class rather than the mode classes avoids depending on when `ok_tasks/` becomes
    importable, and leaves upstream's task files untouched.
    """
    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, leaving the stock settings alone")
        return

    # Two seams, because the framework builds tasks two different ways. Tasks registered in `src/config.py`
    # get `post_init`, while the modes discovered under `ok_tasks/` are custom tasks and only get
    # `after_init`. Hooking both covers every task, and applying twice is harmless.
    for hook in ("post_init", "after_init"):
        original = getattr(BaseTask, hook, None)
        if original is None:
            logger.warning(f"BaseTask has no {hook}, skipping that hook")
            continue

        def patched(self, *args, _original=original, **kwargs):
            result = _original(self, *args, **kwargs)
            try:
                apply_to(self)
            except Exception as error:
                logger.warning(f"could not apply Global client settings to {self.__class__.__name__}: {error}")
            return result

        setattr(BaseTask, hook, patched)
    logger.info("Global client settings hooked into task setup")
