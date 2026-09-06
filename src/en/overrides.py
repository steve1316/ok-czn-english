"""Re-shape the mode settings for the Global (English) client.

Upstream's task files ship one Chinese player's build as defaults and ask the user to type entity names by
hand. On the Global client those Chinese names can never match what the OCR reads, so they are replaced with
English defaults and, wherever the value set is knowable, with pick-from-a-list widgets built from the game's
own localization table.

This hooks `BaseTask.load_config` and runs *before* it. That is the seam upstream itself uses - `ChaosMode`
overrides `load_config` to run its migrations and then calls `super()` - and it matters here for two reasons:
it is the one call that happens exactly once per task, and it happens before `Config` is built, so a fresh
install is seeded with the English defaults rather than written in Chinese and corrected afterwards.

`ok_tasks/ChaosMode.py` and `ok_tasks/SortieMode.py` stay byte-identical to upstream, so a merge never
conflicts in them.

Two rules decide whether a setting can become a pick-list:

- The value must be compared against **OCR text**. Card, equipment and combatant names are, so those become
  lists of English names. Route Priority is not - its values are internal labels produced from template
  feature names (`enemy_in_map` -> `小怪`), so they stay as upstream writes them and are only translated for
  display.
- The match must be on a **whole name**. Epiphany Priority, the Persona settings and Farm Starting Card are
  matched as subsequences of `name + description`, which is how a user targets an effect rather than a card.
  Restricting those to full card names would take that away, so they stay free text.
"""

from ok import Logger
from ok.util.config import Config
from ok.util.file import get_relative_path, read_json_file, write_json_file

from src.en.game_data import CARDS, COMBATANTS, EQUIPMENT
from src.en.framework import import_ui

logger = Logger.get_logger(__name__)

# Bump this when the settings below change shape enough that a saved config should be re-seeded. It is stamped
# into the config file, and the leading underscore keeps it out of exported config codes.
SETTINGS_VERSION = 1
VERSION_KEY = "_en_settings_version"

# Route Priority values are internal labels, never OCR text, so they must stay exactly as upstream writes
# them. `ok.po` translates them for display, and ModifyListDialog stores the canonical value.
ROUTE_NODES = ["休息", "事件", "小怪", "精英"]
KEEPS_CHINESE = {"路线优先级"}
# Game Language stays a real setting for the Chinese clients. English behaves like Simplified Chinese, since
# `_get_game_text` falls back to the untranslated literal when a language has no map file.
GAME_LANGUAGES = ["English", "简体中文", "繁体中文"]

# List settings the user picks from, keyed by config name -> the roster it draws on.
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
# Single-choice settings, keyed by config name -> the roster and the default to pick from it.
SINGLE_CHOICE = {
    "游戏语言": (GAME_LANGUAGES, "English"),
    "刷存档主战员": (COMBATANTS, "Heidemarie"),
}
# A setting this fork adds rather than re-shapes, so its key is English like the rest of the fork's own
# code. Play Priority is declared by Sortie alone, which makes it the marker for the only mode that has
# to choose its own cards, and so the only one this belongs on.
SMART_CARD_PLAY = "Smart Card Play"
PLAYS_ITS_OWN_CARDS = "出牌优先级"
# Free-text settings whose Chinese default cannot carry over. Cleared so the user fills them from what the
# client actually shows, rather than inheriting a value that can never match.
CLEARED_TEXT = ["指定面具卡牌", "面具卡牌刻印", "刷初始卡牌"]
CLEARED_LISTS = ["闪光优先级", "任务优先级", "拉黑任务"]

# Every setting this module owns, and so may re-seed when the saved config predates it.
MANAGED_KEYS = set(LIST_OPTIONS) | set(SINGLE_CHOICE) | set(CLEARED_TEXT) | set(CLEARED_LISTS)

# Help text, in the client's own wording.
DESCRIPTIONS = {
    "游戏语言": "Leave this on English for the Global client. The Chinese clients need Simplified or Traditional.",
    "路线优先级": "Which map node to head for first. Safe Zones restore health, Unidentified Areas run an event.",
    "移除卡牌列表": "Cards to delete from the deck whenever a removal is offered.",
    "复制卡牌列表": "Cards to duplicate whenever a copy is offered.",
    "闪光卡牌列表": "Cards to spend an Epiphany on.",
    "闪光优先级": "Epiphany targets, matched loosely against a card's name and its description, so a few keywords are enough. Order matters.",
    "需要冥想的卡牌": "The exact cards to meditate on, each taken once per run. Nothing happens until Credits pass the figure in Meditate Above This Many Credits.",
    "卡牌奖励优先级": "Preferred cards when a reward offers a choice.",
    "获得卡牌优先级": "Preferred cards when the run offers a card to obtain.",
    "丢弃卡牌优先级": "Cards to throw away first when the run asks you to discard.",
    "出牌优先级": "Order to play cards in battle. Needs shortcut key display turned on in the game's settings.",
    SMART_CARD_PLAY: "Choose battle cards on what they actually do - what they cost, what kind they are, and"
                     " which attribute an enemy is weak to - rather than pressing every hotkey in turn. Your"
                     " Play Priority list still comes first and is unaffected; this decides the cards it does"
                     " not mention. Turn it off to go back to upstream's behaviour.",
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
    "任务优先级": "Preferred options inside an Unidentified Area, best first, matched loosely against the option's description rather than its title - so prefer distinctive wording, since a short word matches far more than you expect. Your Equipment Slot priorities are tried ahead of this list, and an area that matches nothing is picked at random.",
    "拉黑任务": "Never take an Unidentified Area option whose description matches one of these, so an entry like Curse skips anything handing you a Curse Card. If blocking would leave nothing to choose from, the list is ignored for that one screen.",
    "领取奖励(只使用验证卡)": "Takes the Additional Loot the Settlement screen offers, spending one of the four Loot Certification Cards issued each week. Turns itself off once they run out, so a run never pays Aether for loot.",
    "领取奖励": "Claims the Chaos loot offered at the end of a sortie. Turns itself off when there is not enough Aether left to keep claiming.",
    "多少信用点以上冥想": "Only meditate once Credits reach this much, so a run keeps enough to spend elsewhere.",
    "治疗崩溃": "Visit the Epione Center when a Combatant hits a Mental Breakdown, instead of running on under the Stress.",
    "生命值大于多少优先闪光(百分比)": "Only spend an Epiphany while the Combatant's health is above this percentage.",
    "第几层boss前自动暂停": "Stop and hand back control before the boss on this floor. Never Pause runs the whole map unattended.",
    "几轮后停止(0为不停止)": "Stop the bot after this many finished runs. Zero keeps it going.",
    "配置操作": "Import or export this mode's settings as a shareable code, and save or switch between local presets.",
    "存储数据价值大于等于多少层级": "Only keep a run whose Save Data Value reaches this tier.",
    "保留大于多少TB的存档": "Only keep save data above this size.",
    "优先使用金币治疗": "Always pay Credits for counselling at the Epione Center. Left off, a Communication Pass is spent when you have one and Credits only when you do not.",
    "进入商店": "Visit the Dellang Shop when a Safe Zone offers one. It pays to remove a card first, up to five a run, then buys from your Card Reward Priority and Equipment Slot lists.",
    "优先移除基础牌": "Clear basic cards out of the deck before anything else.",
    "只打第一层": "Leave after the first floor instead of running the whole map.",
}

_applied = False


def reshape(task):
    """Replace one task's Chinese defaults and widgets with their Global-client equivalents.

    Args:
        task: The task being configured, before its `Config` exists.
    """
    for key, options in LIST_OPTIONS.items():
        if key not in task.default_config:
            continue
        # The roster is shared rather than copied: ModifyListItem only ever reads it, and the card list is
        # long enough that copying it per setting per task adds up to nothing useful.
        task.config_type[key] = {"type": "drop_down", "options_available": options}
        if key not in KEEPS_CHINESE:
            task.default_config[key] = []

    for key, (options, default) in SINGLE_CHOICE.items():
        if key in task.default_config:
            task.config_type[key] = {"type": "drop_down", "options": options}
            task.default_config[key] = default

    for key in CLEARED_TEXT:
        if key in task.default_config:
            task.default_config[key] = ""
            # Pin the widget: the factory picks by default length, and a translated string over 16 characters
            # would silently become a multi-line text box.
            task.config_type[key] = {"type": "line_edit"}

    for key in CLEARED_LISTS:
        if key in task.default_config:
            task.default_config[key] = []

    # Added rather than re-shaped, so it needs no migration: `Config` seeds a key it has never saved from
    # `default_config`, and an existing config simply gains it switched on.
    if PLAYS_ITS_OWN_CARDS in task.default_config:
        task.default_config[SMART_CARD_PLAY] = True

    for key, text in DESCRIPTIONS.items():
        if key in task.default_config:
            task.config_description[key] = text

    # `Config` rebuilds the saved file from `default_config` plus the saved values, so a key it does not know
    # about is dropped - which would lose the migration stamp and re-seed on every launch. The leading
    # underscore keeps it out of the settings UI and out of exported config codes.
    task.default_config[VERSION_KEY] = SETTINGS_VERSION

    # Upstream leaves ok-script's scaffold placeholder here, a bare link to the framework repo. The button
    # hides itself when this is empty. Only the modes under `ok_tasks/` are ours to strip.
    if getattr(task, "is_custom", False):
        task.instructions = None


def migrate_saved_config(task):
    """Drop settings saved before this fork re-shaped them, once.

    A config written against upstream's defaults holds Chinese card and combatant names that can never match
    English OCR, so it has to be re-seeded. This runs before `Config` is built, editing the file the same way
    upstream's own migrations in `ok_tasks/config_io.py` do, and stamps a version so it happens exactly once.
    Anything the user sets afterwards is left alone, including a deliberately Chinese value.

    Args:
        task: The task whose saved config should be checked.
    """
    path = get_relative_path(Config.config_folder, f"{task.__class__.__name__}.json")
    data = read_json_file(path)
    if not isinstance(data, dict) or data.get(VERSION_KEY) == SETTINGS_VERSION:
        return

    dropped = [key for key in MANAGED_KEYS if key in data and key not in KEEPS_CHINESE]
    for key in dropped:
        del data[key]
    data[VERSION_KEY] = SETTINGS_VERSION
    write_json_file(path, data)
    if dropped:
        logger.info(f"re-seeded {len(dropped)} setting(s) of {task.__class__.__name__} for the Global client")


def translate_notifications():
    """Let toast notifications use the app translation catalog.

    `MainWindow.show_notification` only runs its text through Qt's own context, which holds the framework's
    strings. Everything this fork translates lives in the gettext catalog, so task names would otherwise reach
    the toast untranslated. A string with no catalog entry comes back unchanged.
    """
    main_window = import_ui("MainWindow", "MainWindow")
    if main_window is None:
        return
    original_show = main_window.show_notification

    def patched_show(self, message, title=None, *args, **kwargs):
        # ok-script has grown arguments here before, so forward the rest instead of respelling them.
        from ok import og

        try:
            if message:
                message = og.app.tr(message)
            if title:
                title = og.app.tr(title)
        except Exception as error:
            logger.warning(f"could not translate notification: {error}")
        original_show(self, message, title, *args, **kwargs)

    main_window.show_notification = patched_show
    logger.info("notifications routed through the translation catalog")

def apply():
    """Wrap `BaseTask.load_config` so every task is re-shaped before its config is built."""
    global _applied
    if _applied:
        return
    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, leaving the stock settings alone")
        return

    original_load_config = BaseTask.load_config

    def patched_load_config(self):
        try:
            reshape(self)
            migrate_saved_config(self)
        except Exception as error:
            logger.warning(f"could not apply Global client settings to {self.__class__.__name__}: {error}")
        original_load_config(self)

    BaseTask.load_config = patched_load_config
    _applied = True
    logger.info("Global client settings hooked into task setup")
    translate_notifications()
