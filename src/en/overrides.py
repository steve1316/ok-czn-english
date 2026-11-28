"""Re-shape the mode settings for the Global (English) client.

Upstream ships one Chinese player's build as defaults and asks the user to type entity names by hand. Those
Chinese names can never match what English OCR reads, so they are replaced with English defaults and, wherever
the value set is knowable, with pick-from-a-list widgets built from the game's own localization table.
"""

from ok import Logger
from ok.util.config import Config
from ok.util.file import get_relative_path, read_json_file, write_json_file

from src.en.desire import DEFAULT_FACTION, FACTIONS
from src.en.etched_memory import BONUSES, ENTER_MEMORY_END, ETCHED_MEMORY, KEEP_BONUS, MEMORIES, MEMORY_BONUS
from src.en.game_data import CARDS, COMBATANTS, EQUIPMENT, RISK_MODIFIERS, SORTIE_LEVELS
from src.en.framework import import_ui
from src.en.game_language import GAME_LANGUAGES, MODE_KEY
from src.en.heal import PAY_CREDITS
from src.en.reobserve import DEFAULT_BLACKLIST, MODIFIER_BLACKLIST, MODIFIERS, REOBSERVE
from src.en.meditation import MAX_STRESS, MEDITATE, MIN_HP_PERCENT
from src.en.rest import SHOP_SETTING
from src.en.shop import BUY_CARDS, OLD_BUY_CARDS, PAID_THRESHOLD, TAKE_MONSTER_REWARDS
from src.en.zero_system import (ANY, CHAOS_MERGE, CODEX, CODEX_MERGE, CODEX_OPTIONS, CODEX_SEASON, DEFAULT_MAX_MERGES, MAX_MERGES, MERGE_OPTIONS,
                                 NORMAL_MERGE, SEASON_OPTIONS)

logger = Logger.get_logger(__name__)

# Bump this when the settings below change shape enough that a saved config should be re-seeded. It is stamped
# into the config file, and the leading underscore keeps it out of the settings UI.
SETTINGS_VERSION = 1
VERSION_KEY = "_en_settings_version"
# Fork settings saved under an older key, as old -> new. A saved value moves across, since `Config` would drop the old key and re-seed the new one.
RENAMED = {OLD_BUY_CARDS: BUY_CARDS}

# Route Priority values are internal labels, never OCR text, so they must stay exactly as upstream writes
# them. `ok.po` translates them for display, and ModifyListDialog stores the canonical value.
ROUTE_NODES = ["休息", "事件", "小怪", "精英"]
KEEPS_CHINESE = {"路线优先级"}

# A setting this fork adds rather than re-shapes, so its key is English like the rest of the fork's own
# code. Play Priority is declared by Sortie alone, which makes it the marker for the only mode that has
# to choose its own cards, and so the only one this belongs on.
SMART_CARD_PLAY = "Smart Card Play"
PLAYS_ITS_OWN_CARDS = "出牌优先级"
# Upstream settings taken off both modes. `Config` drops a saved key it no longer declares, so upstream reads its own default.
# Upstream's Meditation list and threshold are replaced by `MEDITATE`. Its Credits switch is read as on by `heal.py`.
# Its discard list is read nowhere. Its lead combatant list is replaced by `DRAFTED_COMBATANT`.
DROPPED = ("优先移除基础牌", "需要冥想的卡牌", "多少信用点以上冥想", PAY_CREDITS, "丢弃卡牌优先级", "出战主战员优先级")
# The combatant whose save data the run farms. `src/en/navigation.py` reads it to recognise the tab. Only Chaos
# declares it, which makes it the marker for Chaos-only settings.
FARMED_COMBATANT = "刷存档主战员"
# The farmed combatant's opt-out. Stored as is rather than as an empty string, because upstream skips the Combatants
# screen for an empty name, and that visit is where the team and its equipment are read. No combatant carries it,
# so the visit binds nobody.
NO_COMBATANT = "(none)"
# Season 4's Desire faction, added the same way and for the same reason: it postdates the settings upstream
# ships. Desire cards only exist in Chaos, so it is anchored on `FARMED_COMBATANT` rather than a list Sortie shares.
DESIRE_FACTION = "Desire Faction"
# Extract every non-Mythic piece for Credits instead of equipping it. Here rather than in `src/en/equipment.py`, which imports this module.
EXTRACT_SPARE = "Extract Spare Equipment"
# The Lv.80 Risk Modifiers to turn on before each Sortie run. Here rather than in `src/en/sortie_loop.py`, which imports this module.
RISK_PICKS = "Risk Modifiers"
# The Sortie tier to start each run on, stepped to from whatever the lobby shows. `KEEP_LEVEL` leaves the lobby's tier alone.
SORTIE_LEVEL = "Sortie Level"
KEEP_LEVEL = "Keep current"
LEVEL_OPTIONS = [KEEP_LEVEL, *(f"Lv.{level}" for level in SORTIE_LEVELS)]
# The combatant Sortie assigns to the formation's empty slot. `AUTO_DRAFT` presses Assign on the game's own pick, the week's red
# Drafted Combatant. Both here rather than in `src/en/sortie_loop.py`, which imports this module.
DRAFTED_COMBATANT = "Drafted Combatant"
AUTO_DRAFT = "Auto"
# Whether Sortie runs with the formation's Hardcore Mode switch on.
HARDCORE = "Hardcore Mode"
# Fork settings added right under the upstream row they belong with, as `(key, default, anchor)`. Both modes declare the first two anchors.
# Only Sortie declares Blocked Combatants and Combatant Priority, which keeps the rest off Chaos.
ADDED_UNDER = ((TAKE_MONSTER_REWARDS, True, "卡牌奖励优先级"), (EXTRACT_SPARE, False, "装备3号位优先级"), (SORTIE_LEVEL, KEEP_LEVEL, "拉黑主战员"), (HARDCORE, False, SORTIE_LEVEL),
               (RISK_PICKS, [], HARDCORE), (DRAFTED_COMBATANT, AUTO_DRAFT, "主战员优先级"))
# List settings the user picks from, keyed by config name -> the roster it draws on.
# Two rules decide whether a setting can become a pick-list. The value must be compared against OCR text - card,
# equipment and combatant names are, while Route Priority's values are internal labels produced from template
# feature names (`enemy_in_map` -> `小怪`) and are only translated for display. And the match must be on a whole
# name: Preferred Epiphany Keywords, the Persona settings and Farm Starting Card are matched as subsequences of
# `name + description`, which is how a user targets an effect rather than a card, so they stay free text.
LIST_OPTIONS = {
    "移除卡牌列表": CARDS,
    "复制卡牌列表": CARDS,
    "闪光卡牌列表": CARDS,
    "卡牌奖励优先级": CARDS,
    "获得卡牌优先级": CARDS,
    PLAYS_ITS_OWN_CARDS: CARDS,
    "装备1号位优先级": EQUIPMENT,
    "装备2号位优先级": EQUIPMENT,
    "装备3号位优先级": EQUIPMENT,
    "主战员优先级": COMBATANTS,
    "拉黑主战员": COMBATANTS,
    "路线优先级": ROUTE_NODES,
}
# Single-choice settings, keyed by config name -> the roster and the default to pick from it.
SINGLE_CHOICE = {
    MODE_KEY: (GAME_LANGUAGES, "English"),
    FARMED_COMBATANT: ([NO_COMBATANT, *COMBATANTS], NO_COMBATANT),
}
# Upstream defaults the fork overrides. A saved config keeps whatever it already holds. The shop's Credit threshold
# is `NEVER_PAY`, so a run never pays to reroll unless the user raises it. Both loot claims start on, and neither one
# spends Aether - `src/en/loot_cards.py` and `src/en/reason.py` skip the loot instead. First Floor Only starts off in both modes.
NEVER_PAY = -1
FORCED_DEFAULTS = {SHOP_SETTING: True, PAID_THRESHOLD: NEVER_PAY, "领取奖励(只使用验证卡)": True, "领取奖励": True, "只打第一层": False}
# Number settings whose range the fork pins. ok-script opens a negative default's range to -999999 and floors a positive
# one at 1, which would stop the save threshold reaching its keep-everything 0.
NUMBER_RANGES = {PAID_THRESHOLD: {"min": NEVER_PAY}, "保留大于多少TB的存档": {"min": 0}}
# Free-text settings whose Chinese default cannot carry over. Cleared so the user fills them from what the
# client actually shows, rather than inheriting a value that can never match.
CLEARED_TEXT = ["指定面具卡牌", "面具卡牌刻印", "指定记忆卡牌", "刷初始卡牌"]
CLEARED_LISTS = ["闪光优先级", "任务优先级", "拉黑任务"]

# Every setting this module owns, and so may re-seed when the saved config predates it.
MANAGED_KEYS = set(LIST_OPTIONS) | set(SINGLE_CHOICE) | set(CLEARED_TEXT) | set(CLEARED_LISTS)

# Help text, in the client's own wording.
DESCRIPTIONS = {
    "路线优先级": "Which map node to head for first. Safe Zones restore health, Unidentified Areas run an event.",
    "移除卡牌列表": "Cards to delete from the deck whenever a removal is offered.",
    "复制卡牌列表": "Cards to duplicate whenever a copy is offered.",
    "闪光卡牌列表": "Cards to spend an Epiphany on.",
    "闪光优先级": "Epiphany targets, matched loosely against a card's name and its description, so a few keywords are enough. Order matters.",
    "卡牌奖励优先级": "Preferred cards when a reward offers a choice.",
    "获得卡牌优先级": "Preferred cards when the run offers a card to obtain.",
    PLAYS_ITS_OWN_CARDS: "Order to play cards in battle. Needs shortcut key display turned on in the game's"
                         " settings.",
    DESIRE_FACTION: "Which Desire faction to build towards. Every Desire card and event option pushes this one higher.",
    SMART_CARD_PLAY: "Choose battle cards by cost, type and effect text instead of pressing every hotkey in turn.",
    "装备1号位优先级": "Preferred equipment for the first slot, best first.",
    "装备2号位优先级": "Preferred equipment for the second slot, best first.",
    "装备3号位优先级": "Preferred equipment for the third slot, best first.",
    "主战员优先级": "Combatants to pick when the run offers a choice.",
    "拉黑主战员": "Combatants to never pick.",
    SORTIE_LEVEL: "The tier each run starts on. Keep current runs whatever the lobby shows.",
    RISK_PICKS: "Lv.80 only. The modifiers to turn on before each run. The rest are turned off.",
    DRAFTED_COMBATANT: f"The combatant to assign when the formation's slot is empty. {AUTO_DRAFT} takes the red Drafted Combatant of the week.",
    HARDCORE: "Turn on Hardcore Mode for increased difficulty and rewards.",
    FARMED_COMBATANT: f"The combatant whose save data is farmed. Pick {NO_COMBATANT} to favour no one.",
    "指定面具卡牌": "The Persona Card to hold out for, matched against its name and description.",
    "面具卡牌刻印": "The Engraving to hold out for on that Persona Card.",
    "指定记忆卡牌": "Free text matched loosely against a Memory card's name and description, on every Memory screen.",
    ETCHED_MEMORY: "Etched Memories to take at the Interior, best first. A page offering none of them is searched again while searches are left.",
    MEMORY_BONUS: f"The bonus to hold out for on the etched Memory Card. {KEEP_BONUS} never processes.",
    REOBSERVE: "Spend event currency to Re-observe the Chaos start page while it carries a blacklisted modifier.",
    MODIFIER_BLACKLIST: "Modifiers to Re-observe or merge away, matched at any level, so Plague covers Plague 1 to 4.",
    CODEX: f"The Codex to hunt for, by its Chaos. {ANY} takes whichever Chaos the slots offer. It must also meet the Minimum Save Data Storage Limit and avoid the {MODIFIER_BLACKLIST}.",
    CODEX_SEASON: "The season the Codex has to carry. Only the seasons the chosen Codex can come with are offered.",
    CODEX_MERGE: f"What a Zero System reroll pays with: Credits for {NORMAL_MERGE}, Chaos Orbs for {CHAOS_MERGE}. Never only picks among the slots.",
    MAX_MERGES: "Merges to spend hunting one Codex. Once they are spent, the best Codex on hand is entered.",
    ENTER_MEMORY_END: "Enter End of Memory after the final boss for the extra fight and its grade upgrade.",
    "刷初始卡牌": "Reroll the starting card until this one appears. Cannot be combined with Farm Gaps.",
    "任务优先级": "Preferred options inside an Unidentified Area, best first, matched loosely against the option's description.",
    "拉黑任务": "Never take an Unidentified Area option whose description matches one of these.",
    "领取奖励(只使用验证卡)": "Takes the Settlement's Additional Loot with one of the four weekly Loot Certification Cards.",
    "领取奖励": "Claims the Chaos Loot at the end of a Sortie with Reason.",
    "治疗崩溃": "Visit the Epione Center when a Combatant hits a Mental Breakdown, instead of running on under the Stress.",
    "生命值大于多少优先闪光(百分比)": "Only spend an Epiphany while the Combatant's health is above this percentage.",
    "第几层boss前自动暂停": "Stop and hand back control before the boss on this floor. Never Pause runs the whole map unattended.",
    "几轮后停止(0为不停止)": "Stop the bot after this many finished runs. Zero keeps it going.",
    "存储数据保存上限大于多少": "Only start a run whose Save Data Storage Limit reaches at least this much, re-rolling until one does.",
    "保留大于多少TB的存档": "After a run, delete each stored save worth this many TB or less. Zero keeps every save.",
    PAID_THRESHOLD: "Pay Credits to reroll the Dellang Shop after its free refreshes, only while holding more than this many.",
    SHOP_SETTING: "Visit the Dellang Shop when a Safe Zone offers one.",
    BUY_CARDS: "Let the Dellang Shop buy cards. Turn it off to spend Credits only on card removals and equipment.",
    TAKE_MONSTER_REWARDS: "Take Monster Cards from a battle's card reward. Turn it off to skip them.",
    EXTRACT_SPARE: "Extract every piece of equipment for Credits instead of equipping it, except a Mythic.",
    MEDITATE: "At a Safe Zone, pay for Meditation to re-roll the Epiphany on a card your build preset pinned.",
    "只打第一层": "Leave after the first floor instead of running the whole map.",
}
# The rest of a description trimmed to two lines, shown when the row is hovered.
TOOLTIPS = {
    "任务优先级": "Prefer distinctive wording, since a short word matches far more than you expect. Your Equipment Slot priorities are tried"
                 " ahead of this list, and an area that matches nothing is picked at random.",
    "拉黑任务": "An entry like Curse skips anything handing you a Curse Card. If blocking would leave nothing to choose from, the list is"
               " ignored for that one screen.",
    "指定记忆卡牌": "It picks the Etched Memory, the Processing option and the bonus Refinement holds out for. Leave it empty to use Etched"
                  " Memory Priority and Memory Bonus instead.",
    MEMORY_BONUS: "Memory Refinement spends its one Processing only when the card holds a different bonus, and takes a reroll only if one"
                  " offers this.",
    REOBSERVE: "Once the currency runs short, the run is entered as it is.",
    ENTER_MEMORY_END: "Turn it off to end the run at the Settlement instead.",
    DESIRE_FACTION: "Reaching 3, 5 or 7 points in a single faction is worth far more than points spread across several.",
    SMART_CARD_PLAY: "Spends each turn's Action Points on the cards worth the most damage, shield and draw, and plays a combatant's cards in"
                     " the order their kit needs. Cards named in Card Play Priority are still played first.",
    "领取奖励(只使用验证卡)": "Once they run out, the rest of that run's Additional Loot is left. It never pays Aether for loot.",
    "领取奖励": "It never charges Reason with Aether, so once Reason runs out the rest of that run's loot is left.",
    "存储数据保存上限大于多少": "This picks the run, it never deletes anything.",
    "保留大于多少TB的存档": "Runs on the Save Data collection screen to free slots. Not the same as Minimum Save Data Storage Limit, which picks"
                       " the run before it starts.",
    PAID_THRESHOLD: "-1 never pays, and 0 pays whenever the price is affordable.",
    SHOP_SETTING: "It pays to remove a card first, up to five a run, then buys from your Card Reward Priority and Equipment Slot lists.",
    TAKE_MONSTER_REWARDS: "Only applies while Card Reward Priority is empty, since a list you fill in is used as written.",
    EXTRACT_SPARE: "The Equipment Slot lists are ignored and the Dellang Shop buys no equipment while this is on.",
    MEDITATE: f"Only with HP at {MIN_HP_PERCENT}% or more and every combatant under {MAX_STRESS:.0%} Stress. With no pinned card, or this off,"
              " the run rests.",
}
# Setup a mode needs before its first run, shown behind its Instructions button. A mode with nothing to set up gets no button.
INSTRUCTIONS = {"ChaosMode": "Turn on the event/dialogue Fast Forward in-game before starting a run."}

_applied = False


def place_under(config, key, anchor):
    """Move a row to sit right under another, when the config declares both.

    Args:
        config: A task's `default_config`, whose order is the order the settings card draws.
        key: The row to move.
        anchor: The row it goes under.
    """
    if key not in config or anchor not in config:
        return
    value = config.pop(key)
    rows = list(config.items())
    under = [name for name, _ in rows].index(anchor) + 1
    config.clear()
    config.update([*rows[:under], (key, value), *rows[under:]])


def reshape(task):
    """Replace one task's Chinese defaults and widgets with their Global-client equivalents.

    Args:
        task: The task being configured, before its `Config` exists.
    """
    for key, options in LIST_OPTIONS.items():
        if key not in task.default_config:
            continue
        # The roster is shared rather than copied: `ListEditor` only ever reads it, and the card list is
        # long enough that copying it per setting per task adds up to nothing useful.
        task.config_type[key] = {"type": "drop_down", "options_available": options}
        if key not in KEEPS_CHINESE:
            task.default_config[key] = []

    for key, (options, default) in SINGLE_CHOICE.items():
        if key in task.default_config:
            task.config_type[key] = {"type": "drop_down", "options": options}
            task.default_config[key] = default
    # Read from the Settings page by `game_language.py`, so the mode card no longer shows it.
    if MODE_KEY in task.config_type:
        task.config_type[MODE_KEY]["hidden"] = True

    for key in CLEARED_TEXT:
        if key in task.default_config:
            task.default_config[key] = ""
            # Pin the widget: the factory picks by default length, and a translated string over 16 characters
            # would silently become a multi-line text box.
            task.config_type[key] = {"type": "line_edit"}

    for key in CLEARED_LISTS:
        if key in task.default_config:
            task.default_config[key] = []

    for key, value in FORCED_DEFAULTS.items():
        if key in task.default_config:
            task.default_config[key] = value

    for key, bounds in NUMBER_RANGES.items():
        if key in task.default_config:
            task.config_type[key] = bounds

    # Added rather than re-shaped, so it needs no migration: `Config` seeds a key it has never saved from
    # `default_config`, and an existing config simply gains it switched on.
    if PLAYS_ITS_OWN_CARDS in task.default_config:
        task.default_config[SMART_CARD_PLAY] = True

    # Both Chaos and Sortie declare the shop switch. Buying cards narrows it, and Meditation is the Safe Zone's other paid choice,
    # so both sit right under it.
    if SHOP_SETTING in task.default_config:
        added = {BUY_CARDS: True, MEDITATE: True}
        rows = [(key, value) for key, value in task.default_config.items() if key not in added]
        under = [key for key, _ in rows].index(SHOP_SETTING) + 1
        task.default_config.clear()
        task.default_config.update([*rows[:under], *added.items(), *rows[under:]])

    for key, default, anchor in ADDED_UNDER:
        if anchor in task.default_config:
            task.default_config[key] = default
            place_under(task.default_config, key, anchor)
    if RISK_PICKS in task.default_config:
        task.config_type[SORTIE_LEVEL] = {"type": "drop_down", "options": LEVEL_OPTIONS}
        task.config_type[RISK_PICKS] = {"type": "drop_down", "options_available": list(RISK_MODIFIERS)}
    if DRAFTED_COMBATANT in task.default_config:
        task.config_type[DRAFTED_COMBATANT] = {"type": "drop_down", "options": [AUTO_DRAFT, *COMBATANTS]}

    if FARMED_COMBATANT in task.default_config:
        task.default_config[DESIRE_FACTION] = DEFAULT_FACTION
        task.config_type[DESIRE_FACTION] = {"type": "drop_down", "options": list(FACTIONS)}
        # Season 5's settings, added for the same reason and anchored the same way.
        task.default_config[ETCHED_MEMORY] = []
        task.config_type[ETCHED_MEMORY] = {"type": "drop_down", "options_available": MEMORIES}
        task.default_config[MEMORY_BONUS] = KEEP_BONUS
        task.config_type[MEMORY_BONUS] = {"type": "drop_down", "options": BONUSES}
        task.default_config[ENTER_MEMORY_END] = True
        task.default_config[REOBSERVE] = True
        task.default_config[MODIFIER_BLACKLIST] = list(DEFAULT_BLACKLIST)
        task.config_type[MODIFIER_BLACKLIST] = {"type": "drop_down", "options_available": MODIFIERS}
        task.default_config[CODEX] = ANY
        task.config_type[CODEX] = {"type": "drop_down", "options": CODEX_OPTIONS}
        # Every season, narrowed to what the chosen Codex can come with once the row is drawn.
        task.default_config[CODEX_SEASON] = ANY
        task.config_type[CODEX_SEASON] = {"type": "drop_down", "options": SEASON_OPTIONS}
        task.default_config[CODEX_MERGE] = NORMAL_MERGE
        task.config_type[CODEX_MERGE] = {"type": "drop_down", "options": MERGE_OPTIONS}
        task.default_config[MAX_MERGES] = DEFAULT_MAX_MERGES

    for key in DROPPED:
        task.default_config.pop(key, None)

    for key, text in DESCRIPTIONS.items():
        if key in task.default_config:
            task.config_description[key] = text

    # `Config` rebuilds the saved file from `default_config` plus the saved values, so a key it does not know
    # about is dropped - which would lose the migration stamp and re-seed on every launch. The leading
    # underscore keeps it out of the settings UI.
    task.default_config[VERSION_KEY] = SETTINGS_VERSION

    # Upstream leaves ok-script's scaffold placeholder here, a bare link to the framework repo. The button
    # hides itself when this is empty. Only the modes under `ok_tasks/` are ours to replace.
    if getattr(task, "is_custom", False):
        task.instructions = INSTRUCTIONS.get(task.__class__.__name__)


def migrate_saved_config(task):
    """Drop settings saved before this fork re-shaped them, once, and carry a renamed setting's value across.

    A config written against upstream's defaults holds Chinese card and combatant names that can never match
    English OCR, so it has to be re-seeded. This runs before `Config` is built, editing the file the same way
    upstream's own migrations in `ok_tasks/config_io.py` do, and stamps a version so it happens exactly once.
    Anything the user sets afterwards is left alone, including a deliberately Chinese value.

    Args:
        task: The task whose saved config should be checked.
    """
    path = get_relative_path(Config.config_folder, f"{task.__class__.__name__}.json")
    data = read_json_file(path)
    if not isinstance(data, dict):
        return
    renamed = [old for old in RENAMED if old in data]
    for old in renamed:
        data.setdefault(RENAMED[old], data.pop(old))
    stale = data.get(VERSION_KEY) != SETTINGS_VERSION
    if not (renamed or stale):
        return

    dropped = [key for key in MANAGED_KEYS if key in data and key not in KEEPS_CHINESE] if stale else []
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
    """Wrap `BaseTask.load_config` so every task is re-shaped before its config is built.

    That is the seam upstream itself uses, since `ChaosMode` overrides `load_config` to run its migrations and
    then calls `super()`. It is the one call that happens exactly once per task, and it happens before `Config`
    is built, so a fresh install is seeded with English defaults rather than written in Chinese and corrected
    afterwards. `ChaosMode.py` and `SortieMode.py` stay byte-identical to upstream, so a merge never conflicts.
    """
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
