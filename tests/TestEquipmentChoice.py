"""Check which combatant a piece of equipment is offered to.

The client marks one row of the Equipment screen "Recommended", and it is the row with a free slot of the
right kind. Upstream cannot see it and falls back to whoever is listed first, so the pick was arbitrary on
every Sortie run. Positions are measured off the captured Equipment screen: three rows pitched 241px apart,
each row's level tag 116px below the banner that would mark it.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.equipment import (  # noqa: E402
    ROW_PITCH, preferring_recommended, recommended_banner, recommended_row,
)

WIDTH, HEIGHT = 1920, 1080
# Where each row's level tag sits, and where the banner sits when that row is the recommended one.
TAG_Y = (345, 588, 827)
BANNER_Y = (229, 472, 711)
TAG_X, BANNER_X = 1210, 1702


class FakeBox:
    """An OCR box positioned by its centre, the way the equipment code reads one."""

    def __init__(self, name, center_x, center_y):
        self.name = name
        self.width, self.height = 100, 30
        self.x = center_x - self.width / 2
        self.y = center_y - self.height / 2


class FakeTask:
    """A task holding one OCR pass of the Equipment screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes
        self.logged = []

    def log_info(self, message):
        self.logged.append(message)


def level_tags():
    """Build the three level tags the handler finds, top to bottom.

    Returns:
        A list of `FakeBox`.
    """
    return [FakeBox("等级", TAG_X, y) for y in TAG_Y]


def equipment_screen(recommended=None):
    """Build the Equipment screen as the reader sees it.

    Args:
        recommended: Index of the row carrying the banner, or None for no banner.

    Returns:
        A `FakeTask`.
    """
    boxes = level_tags()
    if recommended is not None:
        boxes.append(FakeBox("推荐", BANNER_X, BANNER_Y[recommended]))
    return FakeTask(boxes)


class TestRecommendedBanner(unittest.TestCase):
    """Finding the banner in an OCR pass."""

    def test_finds_the_banner(self):
        found = recommended_banner(equipment_screen(recommended=1))
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "推荐")

    def test_returns_none_without_a_banner(self):
        self.assertIsNone(recommended_banner(equipment_screen()))

    def test_ignores_the_word_on_the_left_of_the_screen(self):
        # The banner is drawn over the combatant column. Anything on the card being offered is not it.
        task = FakeTask(level_tags() + [FakeBox("推荐", 300, BANNER_Y[1])])
        self.assertIsNone(recommended_banner(task))


class TestRecommendedRow(unittest.TestCase):
    """Pairing the banner with a row."""

    def test_pairs_the_banner_with_its_own_row(self):
        for index in range(3):
            with self.subTest(row=index):
                task = equipment_screen(recommended=index)
                self.assertEqual(index, recommended_row(task, recommended_banner(task), level_tags()))

    def test_returns_none_when_no_tag_sits_below_the_banner(self):
        # A banner under every tag is a reading that makes no sense, and guessing would equip the wrong row.
        task = FakeTask(level_tags())
        banner = FakeBox("推荐", BANNER_X, 1000)
        self.assertIsNone(recommended_row(task, banner, level_tags()))

    def test_ignores_a_tag_further_away_than_one_row(self):
        banner = FakeBox("推荐", BANNER_X, 100)
        far = [FakeBox("等级", TAG_X, 100 + ROW_PITCH * HEIGHT + 40)]
        task = FakeTask(far)
        self.assertIsNone(recommended_row(task, banner, far))

    def test_returns_none_without_tags(self):
        task = equipment_screen(recommended=1)
        self.assertIsNone(recommended_row(task, recommended_banner(task), []))


class TestPreferringRecommended(unittest.TestCase):
    """What the wrapped handler sees."""

    @staticmethod
    def utils_stub():
        """Build a stand-in for the `utils` module carrying only the seam this patch moves.

        Returns:
            A namespace with `_find_member_level_tags`.
        """
        return types.SimpleNamespace(
            _find_member_level_tags=lambda task_, *args, **kwargs: level_tags(),
        )

    def order_seen(self, task):
        """Run the wrapped handler and report the tag order it was handed.

        Args:
            task: The Equipment screen to run against.

        Returns:
            The centre y of each tag, in the order the handler saw them.
        """
        utils = self.utils_stub()
        seen = []

        def handler(task_):
            seen.append([round(box.y + box.height / 2) for box in utils._find_member_level_tags(task_)])
            return False

        preferring_recommended(handler, utils)(task)
        return seen

    def test_moves_the_recommended_row_to_the_front(self):
        self.assertEqual([[TAG_Y[1], TAG_Y[0], TAG_Y[2]]], self.order_seen(equipment_screen(recommended=1)))

    def test_moves_the_last_row_to_the_front(self):
        self.assertEqual([[TAG_Y[2], TAG_Y[0], TAG_Y[1]]], self.order_seen(equipment_screen(recommended=2)))

    def test_keeps_the_order_when_the_first_row_is_recommended(self):
        self.assertEqual([list(TAG_Y)], self.order_seen(equipment_screen(recommended=0)))

    def test_leaves_the_order_alone_without_a_banner(self):
        self.assertEqual([list(TAG_Y)], self.order_seen(equipment_screen()))

    def test_restores_the_seam_afterwards(self):
        utils = self.utils_stub()
        before = utils._find_member_level_tags
        preferring_recommended(lambda task_: False, utils)(equipment_screen(recommended=1))
        self.assertIs(utils._find_member_level_tags, before)

    def test_restores_the_seam_when_the_handler_raises(self):
        utils = self.utils_stub()
        before = utils._find_member_level_tags

        def raising(task_):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            preferring_recommended(raising, utils)(equipment_screen(recommended=1))
        self.assertIs(utils._find_member_level_tags, before)

    def test_keeps_the_handlers_name(self):
        def handle_equipment(task_):
            return False

        self.assertEqual("handle_equipment",
                         preferring_recommended(handle_equipment, self.utils_stub()).__name__)


if __name__ == "__main__":
    unittest.main()
