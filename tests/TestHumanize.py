"""Check the Input Variance settings on the real settings form, and what they do to clicks, keys and pacing.

The patch is applied to upstream's real `Box` and `PostMessageInteraction`, so a rename upstream fails here. Outside a live run it changes
nothing, which is why `tests/TestCursor.py` keeps its exact points in the same process.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ok.feature.Box import Box  # noqa: E402

from src.en import humanize  # noqa: E402
from src.en.framework import import_ui  # noqa: E402
from tests.fakes import HEIGHT, WIDTH, EchoApp  # noqa: E402

DRAWS = 500
QUIET = humanize.DEFAULTS
OPTION = humanize.human_input_option
# A 1080p frame, the height `SPREAD_PX` is measured at, so a reach in settings is a reach in pixels.
INTERACTION = SimpleNamespace(capture=SimpleNamespace(width=WIDTH, height=HEIGHT))


class TestHumanize(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        humanize.apply()

    def setUp(self):
        humanize._aimed = False

    def test_box_clicks_spread_but_stay_inside_the_middle_of_the_box(self):
        box = Box(100, 200, 200, 40)
        with mock.patch.object(humanize, "settings", return_value=QUIET):
            points = [box.relative_with_variance() for _ in range(DRAWS)]
        # Upstream's variance rounds away, so every click would hit the one centre pixel.
        self.assertGreater(len(set(points)), DRAWS // 10)
        for x, y in points:
            self.assertTrue(130 <= x <= 270 and 206 <= y <= 234, (x, y))

    def test_a_fixed_click_drifts_within_reach_but_a_box_click_is_not_spread_twice(self):
        landed = []
        click = humanize.humanizing_click(lambda self, x, y, **kwargs: landed.append((x, y)))
        with mock.patch.object(humanize, "settings", return_value=QUIET):
            for _ in range(DRAWS):
                click(INTERACTION, 300, 400)
            drifted = list(landed)
            landed.clear()
            Box(100, 200, 200, 40).relative_with_variance()
            click(INTERACTION, 300, 400)
        self.assertGreater(len(set(drifted)), 1)
        reach = QUIET[humanize.SPREAD_PX]
        self.assertTrue(all(abs(x - 300) <= reach and abs(y - 400) <= reach for x, y in drifted))
        self.assertEqual(landed, [(300, 400)])


class TestHumanInputSettings(unittest.TestCase):
    """The section on the real settings form, where a mistyped key would silently lose its row."""

    @classmethod
    def setUpClass(cls):
        # Offscreen has to be chosen before `QApplication` exists.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from ok import og
        from ok.util.config import Config

        cls.qt_app = QApplication.instance() or QApplication([])
        og.app = EchoApp()
        cls.folder = tempfile.TemporaryDirectory()
        config = Config(OPTION.name, OPTION.default_config, folder=cls.folder.name)
        config_form = import_ui("tasks.config_form", "ConfigForm")
        cls.form = config_form(None, config, OPTION.default_config, OPTION.config_description, OPTION.config_type)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_a_number_row_only_shows_while_its_switch_is_on(self):
        rows = self.form.config_widget_by_key
        self.assertEqual(set(rows), set(humanize.DEFAULTS))
        switches = {key: kind["sub_configs"][True] for key, kind in OPTION.config_type.items() if "sub_configs" in kind}
        self.assertTrue(switches)
        for switch, children in switches.items():
            for on in (True, False):
                with self.subTest(switch=switch, on=on):
                    rows[switch].update_config(on)
                    self.assertEqual([rows[child].isHidden() for child in children], [not on] * len(children))

    def test_every_label_is_in_the_chinese_catalog(self):
        msgids = {entry.msgid for entry in polib.pofile(str(REPO_ROOT / "i18n" / "zh_CN" / "LC_MESSAGES" / "ok.po"))}
        for text in (OPTION.name, OPTION.description, *humanize.DEFAULTS, *OPTION.config_description.values()):
            with self.subTest(text=text):
                self.assertIn(text, msgids)


if __name__ == "__main__":
    unittest.main()
