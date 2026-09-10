"""Check that upstream's Chinese comes out as English, and that a line with no entry comes out unchanged.

The table is hand-written and will end up carrying every one of the 454 shapes `ok_tasks/` logs, so the tests
that matter are the ones a wordlist gets wrong: a shape whose pattern does not match the line it renders as,
a replacement that drops one of its interpolations, and a rebase that reworded a line nobody noticed.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scan_log_strings import collect_shapes  # noqa: E402

from src.en import log_text  # noqa: E402
from src.en.log_strings import MESSAGES, TEMPLATES, VALUES  # noqa: E402

CJK = re.compile(r"[一-鿿]")
# A stand-in for one interpolated value, distinctive enough that a pattern cannot match it by accident.
MARKER = "XyZ"
# What `scan_log_strings.py` finds today. Raise it as each file is translated; the last phase makes it total.
MINIMUM_COVERAGE = 0
# The Info rows `log_node_status` and `log_credit` write, which are `info_set` keys rather than logged lines,
# so the extractor never sees them. Upstream renaming one would leave the row Chinese with nothing to say so.
DASHBOARD_KEYS = ("当前信用点", "版本号", "游戏语言", "所处层数，节点，类型", "是否到达关底boss",
                  "是否进入关底boss战斗", "是否已逃脱", "是否已获得特定闪光", "获取刷存档主战员头像",
                  "本局已移除卡牌", "本局已获得中立牌", "装备信息", "当前胜率")


def rendered(shape):
    """Fill a written shape in the way the f-string in `ok_tasks/` would.

    Args:
        shape: A `TEMPLATES` key, with each interpolation written `{}`.

    Returns:
        The line as it would reach the logger, with a marker in each interpolation.
    """
    return shape.replace("{}", MARKER)


class TestTemplates(unittest.TestCase):
    """The half of the table that has to be compiled to be matched."""

    def test_every_template_matches_the_line_it_renders_as(self):
        # The likeliest authoring mistake by far: a Chinese literal carrying a regex character. The very first
        # line in the table has unescaped parens in it, at `点击目标坐标=({}, {})`.
        for shape in TEMPLATES:
            with self.subTest(shape):
                self.assertIsNotNone(log_text.compile_template(shape).match(rendered(shape)))

    def test_a_shape_carrying_regex_characters_is_matched_literally(self):
        # `_move_and_click` writes the most-logged line in the app and it has bare parens in it, so the escape
        # is what stands between the table and a pattern that matches nothing. Pinned with the real shape
        # rather than the entries present today, which happen to carry no regex character at all.
        shape = "页面处理「{}」触发点击事件，点击目标坐标=({}, {})"
        found = log_text.compile_template(shape).match(
            "页面处理「handle_route_selection」触发点击事件，点击目标坐标=(0.805, 0.425)")
        self.assertIsNotNone(found)
        self.assertEqual(("handle_route_selection", "0.805", "0.425"), found.groups())

    def test_every_replacement_uses_all_of_its_interpolations(self):
        # A dropped group silently loses a coordinate or a count from the finished line.
        for shape, english in TEMPLATES.items():
            with self.subTest(shape):
                wanted = shape.count("{}")
                used = {int(field) for field in re.findall(r"\{(\d+)\}", english)}
                self.assertEqual(set(range(wanted)), used)

    def test_no_template_answers_for_another(self):
        log_text._compile_templates()
        for shape, english in TEMPLATES.items():
            with self.subTest(shape):
                self.assertEqual(english.format(*([MARKER] * shape.count("{}"))),
                                 log_text.translate(rendered(shape)))


class TestTranslate(unittest.TestCase):
    """What comes back for something the table does not cover."""

    def test_chinese_with_no_entry_is_handed_back_unchanged(self):
        # Whole lines only. A partial rewrite would read as a bug in the tool where plain Chinese reads as
        # untranslated, and it is what keeps every Chinese value the fork does not own working as it did.
        for text in ("检测到一个没有条目的中文行", "卡牌「未知」"):
            with self.subTest(text):
                self.assertEqual(text, log_text.translate(text))

    def test_anything_that_is_not_text_is_left_alone(self):
        for value in (None, True, 3, 0.5, ["a", "b"], {"k": "v"}):
            with self.subTest(value):
                self.assertIs(value, log_text.translate(value))

    def test_english_is_handed_back_untouched(self):
        self.assertEqual("nothing to do here", log_text.translate("nothing to do here"))

    def test_every_translation_is_english(self):
        for source in (MESSAGES.values(), TEMPLATES.values(), VALUES.values()):
            for english in source:
                with self.subTest(english):
                    self.assertIsNone(CJK.search(english))


class TestReporting(unittest.TestCase):
    """The Info rows, and how often they reach the log."""

    class Task:
        """A task holding just the Info dict and the echo the framework would write."""

        def __init__(self):
            self.info = {}
            self.echoed = []

        def info_set(self, key, value):
            if key not in ("Log", "Error"):
                self.echoed.append(key)
            self.info[key] = value

    def report(self, task, rows):
        """Put rows through the patched `info_set`.

        Args:
            task: The fake task to report on.
            rows: `(key, value)` pairs, in order.
        """
        patched = log_text.reporting(self.Task.info_set)
        for key, value in rows:
            patched(task, key, value)

    def test_a_row_that_did_not_move_is_not_echoed_again(self):
        task = self.Task()
        self.report(task, [("版本号", "dev")] * 5)
        self.assertEqual(["Version"], task.echoed)

    def test_a_row_that_moved_is_echoed(self):
        task = self.Task()
        self.report(task, [("当前信用点", "203"), ("当前信用点", "203"), ("当前信用点", "96")])
        self.assertEqual(["Credits", "Credits"], task.echoed)

    def test_the_tab_still_gets_every_row_whether_or_not_it_moved(self):
        # Withholding the echo must never withhold the row: the tab reads `info`, not the log.
        task = self.Task()
        self.report(task, [("版本号", "dev")] * 3 + [("是否已逃脱", "False")])
        self.assertEqual({"Version": "dev", "Escaped": "False"}, task.info)

    def test_the_rows_a_catalog_could_not_reach_are_english(self):
        # These three are composed at runtime, so `og.app.tr` could never have matched them whole.
        log_text._compile_templates()
        self.assertEqual("floor 2, node 5, Elite Battle Area", log_text.translate("第2层，第5节点，精英"))
        self.assertEqual("slot 1 Anchor, slot 2 empty, slot 3 empty",
                         log_text.translate("1号位：Anchor，2号位：空，3号位：空"))
        self.assertEqual("Meditating on Soul Riff", log_text.translate("冥想：Soul Riff"))

    def test_a_row_reads_the_same_before_the_run_has_a_node_type(self):
        # `node_status` opens with `node_type` empty, so the first status row of every run renders with the
        # last interpolation missing entirely.
        log_text._compile_templates()
        self.assertEqual("floor 1, node 0, ", log_text.translate("第1层，第0节点，"))


class TestUpstreamStillWritesWhatWeTranslate(unittest.TestCase):
    """The rebase alarms. Upstream rewording a line leaves it Chinese, with nothing else to say so."""

    def test_coverage_has_not_regressed(self):
        shapes = collect_shapes()
        covered = len(set(shapes) & (set(MESSAGES) | set(TEMPLATES)))
        self.assertGreaterEqual(covered, MINIMUM_COVERAGE)

    def test_every_dashboard_row_is_still_written_by_upstream(self):
        source = (REPO_ROOT / "ok_tasks" / "utils.py").read_text(encoding="utf-8")
        written = set()
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "info_set" and node.args):
                key = node.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    written.add(key.value)
        for key in DASHBOARD_KEYS:
            with self.subTest(key):
                self.assertIn(key, written)


if __name__ == "__main__":
    unittest.main()
