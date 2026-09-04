"""Guard the Global-client settings overrides.

`src/en/overrides.py` re-shapes the mode settings after the framework builds them. Nothing here talks to the
GUI - these assert the three things that fail silently at runtime if they drift: an entity name leaking into
the reverse OCR catalog, a route value getting translated, and a long default turning a text box into a
multi-line editor.
"""

import re
import sys
import unittest
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import overrides  # noqa: E402
from src.en.game_data import CARDS, COMBATANTS, EQUIPMENT, NODE_TYPES  # noqa: E402

OCR_PO = REPO_ROOT / "i18n" / "en_US" / "LC_MESSAGES" / "ocr.po"
# Above this length the widget factory turns a string setting into a multi-line text box.
MAX_LINE_EDIT_DEFAULT = 16
# Words that are both a UI button and an entity name. gettext rewrites by exact string with no idea where the
# text sat on screen, so one of the two has to lose. Each entry here is a decision, not an oversight.
REVIEWED_COLLISIONS = {
    # The button that leaves a run. handle_escape only reads it at a fixed point in the bottom-right corner,
    # and abandoning a run matters more to the automation than targeting one card out of 1,472.
    "Retreat",
}


class FakeTask:
    """Stands in for a mode task, carrying the three attributes the settings are built from."""

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
        }
        self.config_type = {}
        self.config_description = {}
        self.instructions = "placeholder"


def configured():
    """Build a task and run the overrides over it.

    Returns:
        The configured `FakeTask`.
    """
    task = FakeTask()
    overrides.apply_to(task)
    return task


class TestGameData(unittest.TestCase):

    def test_rosters_are_populated_and_unique(self):
        """A silently empty roster would render an unusable dropdown."""
        for name, roster in (("CARDS", CARDS), ("EQUIPMENT", EQUIPMENT), ("COMBATANTS", COMBATANTS)):
            with self.subTest(roster=name):
                self.assertGreater(len(roster), 20, f"{name} looks truncated")
                self.assertEqual(len(roster), len(set(roster)), f"{name} has duplicates")
                self.assertTrue(all(entry.strip() for entry in roster), f"{name} has blank entries")

    def test_node_types_cover_the_route_options(self):
        """Route Priority is described with node-type names, so those must exist in the game data."""
        for expected in ("Safe Zones", "Unidentified Area", "Normal Battle Area", "Elite Battle Area"):
            self.assertIn(expected, NODE_TYPES)


class TestOverrides(unittest.TestCase):

    def test_game_language_defaults_to_english(self):
        task = configured()
        self.assertEqual("English", task.default_config["游戏语言"])
        self.assertIn("English", task.config_type["游戏语言"]["options"])

    def test_entity_settings_become_pick_lists(self):
        """Typing an entity name by hand is how a config silently stops matching."""
        task = configured()
        for key, roster in (("移除卡牌列表", CARDS), ("装备1号位优先级", EQUIPMENT), ("出战主战员优先级", COMBATANTS)):
            with self.subTest(key=key):
                self.assertEqual(list(roster), task.config_type[key]["options_available"])
                self.assertEqual([], task.default_config[key], "Chinese defaults cannot match English OCR")

    def test_route_priority_keeps_its_canonical_values(self):
        """Route values are internal labels built from template feature names, never text read off the screen.

        `recognize_map_connections` maps `enemy_in_map` to `小怪`, so translating the stored value would stop
        the route search matching. Only the display is translated, through `ok.po`.
        """
        task = configured()
        self.assertEqual(["休息", "事件", "小怪", "精英"], task.default_config["路线优先级"])
        self.assertEqual(["休息", "事件", "小怪", "精英"], task.config_type["路线优先级"]["options_available"])

    def test_subsequence_settings_stay_free_text(self):
        """Epiphany Priority matches fragments of a card's name and description, so a fixed list would break it."""
        task = configured()
        self.assertNotIn("闪光优先级", task.config_type)

    def test_long_string_defaults_declare_a_line_edit(self):
        """The widget is chosen from the default's length, and over 16 characters silently becomes a text box."""
        task = configured()
        for key, value in task.default_config.items():
            if isinstance(value, str) and len(value) > MAX_LINE_EDIT_DEFAULT:
                with self.subTest(key=key):
                    self.assertEqual("line_edit", task.config_type.get(key, {}).get("type"),
                                     f"'{key}' defaults to {len(value)} characters and needs an explicit line_edit")

    def test_instructions_are_cleared(self):
        """Upstream leaves ok-script's scaffold placeholder here, which tells the user nothing."""
        self.assertIsNone(configured().instructions)

    def test_descriptions_are_english(self):
        task = configured()
        self.assertTrue(task.config_description, "no descriptions were applied")
        for key, text in task.config_description.items():
            with self.subTest(key=key):
                self.assertIsNone(re.search(r"[一-鿿]", text), f"'{key}' description still has Chinese")


class TestCatalogSeparation(unittest.TestCase):

    def test_ocr_catalog_holds_no_entity_names(self):
        """`ocr.po` rewrites English into Chinese, so an entity name there would stop card matching entirely.

        Entity names must reach the handlers as the English the OCR read, because the user's config is English
        too. Only fixed UI anchors belong in that catalog.
        """
        entities = set(CARDS) | set(EQUIPMENT) | set(COMBATANTS)
        for entry in polib.pofile(str(OCR_PO)):
            if entry.msgid and entry.msgid not in REVIEWED_COLLISIONS:
                with self.subTest(msgid=entry.msgid):
                    self.assertNotIn(entry.msgid, entities, f"'{entry.msgid}' is an entity name and must not be rewritten")

    def test_every_reviewed_collision_is_still_real(self):
        """Drop an entry from the allowlist once it stops colliding, so the list stays a record of live tradeoffs."""
        entities = set(CARDS) | set(EQUIPMENT) | set(COMBATANTS)
        catalog = {e.msgid for e in polib.pofile(str(OCR_PO)) if e.msgid}
        for word in REVIEWED_COLLISIONS:
            with self.subTest(word=word):
                self.assertIn(word, catalog, f"'{word}' is no longer in ocr.po, remove it from the allowlist")
                self.assertIn(word, entities, f"'{word}' no longer collides with an entity name, remove it")


if __name__ == "__main__":
    unittest.main()
