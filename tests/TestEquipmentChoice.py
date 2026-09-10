"""Check which combatant a piece of equipment is offered to.

The client marks one row of the Equipment screen "Recommended", and it is the row with a free slot of the
right kind. Upstream cannot see it and falls back to whoever is listed first, so the pick was arbitrary on
every Sortie run. Positions are measured off the captured Equipment screen: three rows pitched 241px apart,
each row's level tag 116px below the banner that would mark it.
"""

import sys
import types
import unittest
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.equipment import (  # noqa: E402
    EQUIPMENT_FLOOR, ROW_PITCH, SLOTS, bare_slots, insisting_on_mythic, mythic_offer,
    preferring_recommended, recommended_banner, recommended_row, refusing_equipment, remembering_slots,
)

WIDTH, HEIGHT = 1920, 1080
# Where each row's level tag sits, and where the banner sits when that row is the recommended one.
TAG_Y = (345, 588, 827)
BANNER_Y = (229, 472, 711)
TAG_X, BANNER_X = 1210, 1702
# The caption the client prints under a Mythic piece, and where it sits.
MYTHIC_CAPTION = "Combatants are limited to 1 piece of Mythic-grade equipment."
CAPTION_X, CAPTION_Y = 586, 780
# What upstream calls its top quality bucket. On this client that bucket is Mythic.
TOP_QUALITY = "传说"


# The equipment code reads pixel positions, not fractions.
FakeBox = partial(Box, width=100, height=30, units="pixels")


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

class TestMythicOffer(unittest.TestCase):
    """Spotting a Mythic piece."""

    def test_reads_the_caption(self):
        self.assertTrue(mythic_offer(FakeTask([FakeBox(MYTHIC_CAPTION, CAPTION_X, CAPTION_Y)])))

    def test_ignores_a_screen_without_it(self):
        self.assertFalse(mythic_offer(equipment_screen(recommended=1)))

    def test_ignores_the_word_outside_the_caption_area(self):
        # The combatant column is full of item names; only the caption under the offered piece counts.
        self.assertFalse(mythic_offer(FakeTask([FakeBox(MYTHIC_CAPTION, 1700, 300)])))

class TestInsistingOnMythic(unittest.TestCase):
    """Whether a Mythic piece survives the user's equipment priority list."""

    @staticmethod
    def utils_stub(answer):
        """Build a stand-in carrying only the decision this patch overrides.

        Args:
            answer: What upstream's comparison returns.

        Returns:
            A namespace with `_should_install_equipment`.
        """
        return types.SimpleNamespace(
            _should_install_equipment=lambda task_, name, quality, new: answer,
        )

    def decide(self, task, answer, current_quality, new_quality=TOP_QUALITY):
        """Run the wrapped handler and report the decision it reached.

        Args:
            task: The Equipment screen to run against.
            answer: What upstream's comparison would have returned.
            current_quality: The quality already in that slot.
            new_quality: The quality of the piece being offered.

        Returns:
            The `(install, reason)` pair upstream was handed.
        """
        utils = self.utils_stub(answer)
        reached = []

        def handler(task_):
            reached.append(utils._should_install_equipment(
                task_, "Raider's Scanning Gear", current_quality, {"quality": new_quality}))
            return False

        insisting_on_mythic(handler, utils)(task)
        return reached[0]

    def screen(self):
        """Build an Equipment screen offering a Mythic piece.

        Returns:
            A `FakeTask`.
        """
        return FakeTask(level_tags() + [FakeBox(MYTHIC_CAPTION, CAPTION_X, CAPTION_Y)])

    def test_overrides_a_refusal_from_the_priority_list(self):
        install, reason = self.decide(self.screen(), (False, "当前装备配置优先级更高"), "史诗")
        self.assertTrue(install)
        self.assertIn("Mythic", reason)

    def test_leaves_an_acceptance_alone(self):
        self.assertEqual((True, "配置优先级更高"),
                         self.decide(self.screen(), (True, "配置优先级更高"), "史诗"))

    def test_does_not_swap_one_mythic_for_another(self):
        # The slot already holds the best thing there is, so replacing it gains nothing.
        self.assertEqual((False, "品质传说不高于传说"),
                         self.decide(self.screen(), (False, "品质传说不高于传说"), TOP_QUALITY))

    def test_leaves_a_plain_piece_alone(self):
        self.assertEqual((False, "当前装备配置优先级更高"),
                         self.decide(equipment_screen(), (False, "当前装备配置优先级更高"), "史诗",
                                     new_quality="史诗"))

if __name__ == "__main__":
    unittest.main()


class TestBareSlots(unittest.TestCase):
    """Reading back which equipment slots are still empty on somebody.

    Upstream keeps this for the save-data combatant alone, so a slot standing empty on either of the other
    two counted as filled. All three are read here, because a piece bought for a bare slot is worth far more
    than one that replaces something already worn - and the run is being asked not to spend on the latter.
    """

    def test_nothing_seen_yet_reads_as_every_slot_bare(self):
        # A run opens with all three combatants stripped, so this is the truth and not merely permissive.
        self.assertEqual({0, 1, 2}, bare_slots(FakeTask([])))

    def test_a_slot_empty_on_anybody_counts(self):
        task = FakeTask([])
        setattr(task, SLOTS, [["传说", "传说", "传说"],
                              ["传说", "", "传说"],
                              ["传说", "传说", "传说"]])
        self.assertEqual({1}, bare_slots(task))

    def test_a_full_team_leaves_nothing_bare(self):
        task = FakeTask([])
        setattr(task, SLOTS, [["传说"] * 3] * 3)
        self.assertEqual(set(), bare_slots(task))

    def test_a_slot_that_could_not_be_read_is_not_called_bare(self):
        # The colour read hands back None when it cannot see the frame, which is not the same as empty.
        task = FakeTask([])
        setattr(task, SLOTS, [[None, None, None]])
        self.assertEqual(set(), bare_slots(task))


class TestRememberingSlots(unittest.TestCase):
    """Reading every combatant's slots off the screen that shows all three."""

    def stubs(self, rows=3):
        """Build a `utils` stand-in for the install screen.

        Args:
            rows: How many combatant rows the screen shows.

        Returns:
            A `(utils, seen)` pair, where `seen` records which rows were read for their slots.
        """
        seen = []

        def find_tags(task_, region, page=None):
            return [f"row{index}" for index in range(rows)]

        def qualities(task_, row):
            seen.append(row)
            return ["", "传说", ""]

        return types.SimpleNamespace(_find_member_level_tags=find_tags,
                                     _member_equipment_qualities=qualities), seen

    def handler(self, utils):
        """Build a stand-in for upstream, which reads the rows once and equips one of them."""
        def handle(task_):
            utils._find_member_level_tags(task_, (0.6, 0.3, 0.7, 0.8), page="安装装备页面")
            return True

        handle.__name__ = "handle_equipment"
        return handle

    def test_every_row_is_read(self):
        utils, seen = self.stubs()
        task = FakeTask([])
        remembering_slots(self.handler(utils), utils)(task)
        self.assertEqual(["row0", "row1", "row2"], seen)
        self.assertEqual(3, len(getattr(task, SLOTS)))

    def test_the_slots_are_kept_on_the_task(self):
        utils, _ = self.stubs()
        task = FakeTask([])
        remembering_slots(self.handler(utils), utils)(task)
        self.assertEqual({0, 2}, bare_slots(task))

    def test_a_screen_with_no_rows_leaves_what_was_known(self):
        utils, _ = self.stubs(rows=0)
        task = FakeTask([])
        setattr(task, SLOTS, [["", "", ""]])
        remembering_slots(self.handler(utils), utils)(task)
        self.assertEqual([["", "", ""]], getattr(task, SLOTS))

    def test_the_handler_answer_is_passed_through(self):
        utils, _ = self.stubs()
        self.assertTrue(remembering_slots(self.handler(utils), utils)(FakeTask([])))

class TestRefusingEquipment(unittest.TestCase):
    """What the shop is allowed to spend on equipment.

    Two conditions, both asked for: the run has to be holding real money, and the piece has to be going into
    a slot that is empty on somebody. Upgrading a slot that already has something is what this is meant to
    stop, so a shelf full of Legends is walked past when every slot is spoken for.
    """

    def shop(self, credit, slots=None, listed=("Crimson Sword",)):
        """Build the shop screen and the stubs the gate reads through.

        Args:
            credit: What the run is holding.
            slots: What was last seen of each combatant's slots, or None for a screen never seen.
            listed: What the priority list offers for every slot.

        Returns:
            A `(task, utils, offered, handler)` quadruple, where `offered` collects what upstream was given.
        """
        task = FakeTask([])
        if slots is not None:
            setattr(task, SLOTS, slots)
        offered = {}
        utils = types.SimpleNamespace(
            _equipment_priority=lambda task_, slot: list(listed),
            _get_current_credit=lambda task_: credit,
        )

        def handle(task_):
            offered.update({slot: utils._equipment_priority(task_, slot) for slot in range(3)})
            return True

        handle.__name__ = "handle_shop"
        return task, utils, offered, refusing_equipment(handle, utils)

    def test_a_rich_run_fills_a_bare_slot(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR, slots=[["", "传说", "传说"]])
        handler(task)
        self.assertEqual(["Crimson Sword"], offered[0])

    def test_a_slot_somebody_has_filled_is_not_upgraded(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR, slots=[["", "传说", "传说"]])
        handler(task)
        self.assertEqual([], offered[1])
        self.assertEqual([], offered[2])

    def test_a_poor_run_buys_no_equipment_at_all(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR - 1)
        handler(task)
        self.assertEqual([[], [], []], [offered[slot] for slot in range(3)])

    def test_the_floor_is_inclusive(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR)
        handler(task)
        self.assertEqual(["Crimson Sword"], offered[0])

    def test_a_run_that_has_seen_no_equipment_screen_may_still_buy(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR + 100)
        handler(task)
        self.assertEqual(["Crimson Sword"], offered[0])

    def test_an_empty_list_is_left_empty(self):
        task, _, offered, handler = self.shop(EQUIPMENT_FLOOR + 100, listed=())
        handler(task)
        self.assertEqual([], offered[0])

