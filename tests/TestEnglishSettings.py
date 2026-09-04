"""Guard the Global-client settings overrides.

`src/en/overrides.py` re-shapes the mode settings before the framework builds their config. No widget is built
here - these assert the things that fail silently at runtime if they drift: an entity name leaking into the
reverse OCR catalog, a route value getting translated, a long default turning a text box into a multi-line
editor, the one-shot migration either not running or running forever, and a roster quietly dropping back to the
option picker's slow path.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import overrides, picker  # noqa: E402
from src.en.game_data import CARDS, COMBATANTS, EQUIPMENT, NODE_TYPES  # noqa: E402
from src.en.game_text import DESCRIPTIONS  # noqa: E402
from src.en.framework import import_ui  # noqa: E402

# Resolved the same way the patch resolves it, so the test cannot drift from what ships.
SEARCH_THRESHOLD = import_ui("tasks.ModifyListDialog", "SHOW_SEARCH_OPTIONS_THRESHOLD")

OCR_PO = REPO_ROOT / "i18n" / "en_US" / "LC_MESSAGES" / "ocr.po"
# Above this length the widget factory turns a string setting into a multi-line text box.
MAX_LINE_EDIT_DEFAULT = 16
ENTITY_NAMES = set(CARDS) | set(EQUIPMENT) | set(COMBATANTS)
# Words that are both a UI button and an entity name. gettext rewrites by exact string with no idea where the
# text sat on screen, so one of the two has to lose. Each entry here is a decision, not an oversight.
REVIEWED_COLLISIONS = {
    # The button that leaves a run. handle_escape only reads it at a fixed point in the bottom-right corner,
    # and abandoning a run matters more to the automation than targeting one card out of 1,472.
    "Retreat",
}


class FakeTask:
    """Stands in for a mode task, carrying the attributes the settings are built from."""

    is_custom = True

    def __init__(self):
        self.default_config = {
            "游戏语言": "简体中文",
            "移除卡牌列表": ["剑幕"],
            "装备1号位优先级": ["蚀化臂铠"],
            "出战主战员优先级": ["海德玛丽"],
            "路线优先级": ["休息", "事件", "小怪", "精英"],
            "刷存档主战员": "海德玛丽",
            "指定面具卡牌": "丢弃最多2张卡牌",
            "面具卡牌刻印": "自身攻击卡牌伤害总量提升30%",
            "刷初始卡牌": "",
            "闪光优先级": ["缕光芒80%"],
            "任务优先级": ["复制", "信用点增加", "移除"],
        }
        self.config_type = {}
        self.config_description = {}
        self.instructions = "placeholder"


def reshaped():
    """Build a task and re-shape it.

    Returns:
        The re-shaped `FakeTask`.
    """
    task = FakeTask()
    overrides.reshape(task)
    return task


class TestGameData(unittest.TestCase):

    def test_rosters_are_populated_and_unique(self):
        """A silently empty roster would render an unusable dropdown."""
        for name, roster in (("CARDS", CARDS), ("EQUIPMENT", EQUIPMENT), ("COMBATANTS", COMBATANTS)):
            with self.subTest(roster=name):
                self.assertGreater(len(roster), 20, f"{name} looks truncated")
                self.assertEqual(len(roster), len(set(roster)), f"{name} has duplicates")
                self.assertTrue(all(entry.strip() for entry in roster), f"{name} has blank entries")

    def test_no_combatant_carries_a_description(self):
        """A combatant sharing a name with a card would otherwise hover as that card's effect text.

        `Narja` is both. The generator drops those, so one card loses its tooltip rather than a combatant
        gaining a wrong one.
        """
        overlap = sorted(set(COMBATANTS) & set(DESCRIPTIONS))
        self.assertEqual([], overlap, f"these combatants would show a card's effect: {overlap}")

    def test_descriptions_cover_most_cards_and_equipment(self):
        """A namespace rename upstream would silently empty the tooltips, which nothing else would catch."""
        for name, roster, floor in (("CARDS", CARDS, 0.9), ("EQUIPMENT", EQUIPMENT, 0.8)):
            with self.subTest(roster=name):
                covered = sum(1 for entry in roster if entry in DESCRIPTIONS) / len(roster)
                self.assertGreater(covered, floor, f"only {covered:.0%} of {name} have effect text")

    def test_descriptions_carry_real_numbers(self):
        """If value resolution breaks, every number reverts to `X` and nothing else here would notice.

        About one description in ten still holds an unresolved value, almost all of them the `cs_` families
        that read through a character-stat table the generator does not load. The ceiling is set well above
        that but far below the ~100% a broken resolver would produce.
        """
        vague = sum(1 for text in DESCRIPTIONS.values() if "X" in text) / len(DESCRIPTIONS)
        self.assertLess(vague, 0.15, f"{vague:.0%} of descriptions still have an unresolved value")

    def test_node_types_cover_the_route_options(self):
        """Route Priority is described with node-type names, so those must exist in the game data."""
        for expected in ("Safe Zones", "Unidentified Area", "Normal Battle Area", "Elite Battle Area"):
            self.assertIn(expected, NODE_TYPES)


class TestReshape(unittest.TestCase):

    def test_game_language_defaults_to_english(self):
        task = reshaped()
        self.assertEqual("English", task.default_config["游戏语言"])
        self.assertIn("English", task.config_type["游戏语言"]["options"])

    def test_entity_settings_become_pick_lists(self):
        """Typing an entity name by hand is how a config silently stops matching."""
        task = reshaped()
        for key, roster in (("移除卡牌列表", CARDS), ("装备1号位优先级", EQUIPMENT), ("出战主战员优先级", COMBATANTS)):
            with self.subTest(key=key):
                self.assertEqual(roster, task.config_type[key]["options_available"])
                self.assertEqual([], task.default_config[key], "Chinese defaults cannot match English OCR")

    def test_route_priority_keeps_its_canonical_values(self):
        """Route values are internal labels built from template feature names, never text read off the screen.

        `recognize_map_connections` maps `enemy_in_map` to `小怪`, so translating the stored value would stop
        the route search matching. Only the display is translated, through `ok.po`.
        """
        task = reshaped()
        self.assertEqual(overrides.ROUTE_NODES, task.default_config["路线优先级"])
        self.assertEqual(overrides.ROUTE_NODES, task.config_type["路线优先级"]["options_available"])

    def test_subsequence_settings_stay_free_text(self):
        """Epiphany Priority matches fragments of a card's name and description, so a fixed list would break it."""
        self.assertNotIn("闪光优先级", reshaped().config_type)

    def test_long_string_defaults_declare_a_line_edit(self):
        """The widget is chosen from the default's length, and over 16 characters silently becomes a text box."""
        task = reshaped()
        for key, value in task.default_config.items():
            if isinstance(value, str) and len(value) > MAX_LINE_EDIT_DEFAULT:
                with self.subTest(key=key):
                    self.assertEqual("line_edit", task.config_type.get(key, {}).get("type"),
                                     f"'{key}' defaults to {len(value)} characters and needs an explicit line_edit")

    def test_instructions_are_cleared_only_for_our_modes(self):
        """Upstream leaves ok-script's scaffold placeholder here, but the framework's own tasks are not ours."""
        self.assertIsNone(reshaped().instructions)

        framework_task = FakeTask()
        framework_task.is_custom = False
        overrides.reshape(framework_task)
        self.assertEqual("placeholder", framework_task.instructions)

    def test_the_migration_stamp_is_declared_as_a_default(self):
        """`Config` drops any saved key it does not know about, which would lose the stamp.

        Without this the migration re-seeds the user's settings on every single launch, because the stamp it
        wrote is discarded the moment `Config` rebuilds the file.
        """
        task = reshaped()
        self.assertEqual(overrides.SETTINGS_VERSION, task.default_config.get(overrides.VERSION_KEY))
        self.assertTrue(overrides.VERSION_KEY.startswith("_"), "the stamp must stay out of the settings UI")

    def test_descriptions_are_english(self):
        task = reshaped()
        self.assertTrue(task.config_description, "no descriptions were applied")
        for key, text in task.config_description.items():
            with self.subTest(key=key):
                self.assertFalse(any("一" <= ch <= "鿿" for ch in text), f"'{key}' description has Chinese")


class TestMigration(unittest.TestCase):
    """The saved config is re-seeded exactly once, by version stamp rather than by inspecting the values."""

    def run_migration(self, saved):
        """Run the migration against a throwaway config folder.

        Args:
            saved: The config dict to write before migrating.

        Returns:
            The config dict as it stands afterwards.
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "FakeTask.json"
            path.write_text(json.dumps(saved), encoding="utf-8")
            with mock.patch.object(overrides, "get_relative_path", return_value=str(path)):
                overrides.migrate_saved_config(FakeTask())
            return json.loads(path.read_text(encoding="utf-8"))

    def test_upstream_values_are_dropped_once(self):
        result = self.run_migration({"刷存档主战员": "海德玛丽", "任务优先级": ["复制"], "面具卡牌刻印": "自身攻击"})
        self.assertNotIn("刷存档主战员", result)
        self.assertNotIn("任务优先级", result)
        self.assertNotIn("面具卡牌刻印", result)
        self.assertEqual(overrides.SETTINGS_VERSION, result[overrides.VERSION_KEY])

    def test_route_priority_survives(self):
        """Route Priority is supposed to hold Chinese, so the migration must leave it alone."""
        result = self.run_migration({"路线优先级": ["休息", "事件"]})
        self.assertEqual(["休息", "事件"], result["路线优先级"])

    def test_a_stamped_config_is_left_alone(self):
        """Without the stamp this would wipe the user's settings on every launch."""
        saved = {overrides.VERSION_KEY: overrides.SETTINGS_VERSION, "移除卡牌列表": ["Sword Curtain"]}
        self.assertEqual(saved, self.run_migration(saved))

    def test_unmanaged_settings_survive(self):
        """Only the settings this module re-shapes are its to clear."""
        result = self.run_migration({"几轮后停止(0为不停止)": 5})
        self.assertEqual(5, result["几轮后停止(0为不停止)"])


class TestPicker(unittest.TestCase):
    """Which rosters get the virtualized option list. How it behaves is covered by `TestOptionPicker`."""

    def test_the_fallback_threshold_still_matches_the_framework(self):
        """`apply()` falls back to a local copy of this number, so drift would change which rosters qualify.

        This also catches an upstream rename: the constant would resolve to None and the comparison would fail.
        """
        self.assertEqual(SEARCH_THRESHOLD, picker.FALLBACK_THRESHOLD)

    def test_only_long_rosters_are_virtualized(self):
        """Upstream builds one real PushButton per option, which costs seconds at the sizes this fork ships."""
        rosters = (("CARDS", CARDS, True), ("EQUIPMENT", EQUIPMENT, True), ("COMBATANTS", COMBATANTS, True),
                   ("ROUTE_NODES", overrides.ROUTE_NODES, False), ("free text", None, False))
        for name, roster, expected in rosters:
            with self.subTest(roster=name):
                self.assertEqual(expected, picker.wants_option_list(roster, SEARCH_THRESHOLD))


class TestCatalogSeparation(unittest.TestCase):

    def test_ocr_catalog_holds_no_entity_names(self):
        """`ocr.po` rewrites English into Chinese, so an entity name there would stop card matching entirely.

        Entity names must reach the handlers as the English the OCR read, because the user's config is English
        too. Only fixed UI anchors belong in that catalog.
        """
        for entry in polib.pofile(str(OCR_PO)):
            if entry.msgid and entry.msgid not in REVIEWED_COLLISIONS:
                with self.subTest(msgid=entry.msgid):
                    self.assertNotIn(entry.msgid, ENTITY_NAMES, f"'{entry.msgid}' is an entity name")

    def test_every_reviewed_collision_is_still_real(self):
        """Drop an entry from the allowlist once it stops colliding, so the list stays a record of live tradeoffs."""
        catalog = {e.msgid for e in polib.pofile(str(OCR_PO)) if e.msgid}
        for word in REVIEWED_COLLISIONS:
            with self.subTest(word=word):
                self.assertIn(word, catalog, f"'{word}' is no longer in ocr.po, remove it from the allowlist")
                self.assertIn(word, ENTITY_NAMES, f"'{word}' no longer collides with an entity name, remove it")


if __name__ == "__main__":
    unittest.main()
