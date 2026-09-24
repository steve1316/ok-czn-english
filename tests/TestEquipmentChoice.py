"""Check which combatant a piece of equipment is offered to.

The client marks one row of the Equipment screen "Recommended", and it is the row with a free slot of the
right kind. Upstream cannot see it and falls back to whoever is listed first, so the pick was arbitrary on
every Sortie run. Positions are measured off the captured Equipment screen: three rows pitched 241px apart,
each row's level tag 116px below the banner that would mark it.
"""

import random
import sys
import types
import unittest
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en.rewards import EQUIPMENT_KEYS  # noqa: E402
from src.en.screen import combatant_slot_points  # noqa: E402
from src.en.equipment import (  # noqa: E402
    HANDOVER_X, ROW_PITCH, SLOTS, SPREE_END, SPREE_START, bare_slots, buying_on_spree, has_room_for_mythic,
    insisting_on_mythic, MYTHIC_TIER, UNKNOWN_TIER, install, is_mythic_colour, mythic_offer,
    offering_mythic_where_it_fits, preferring_recommended, reading_the_team_gear, recommended_banner,
    recommended_row, remembering_slots, slot_tier, team_equipment, worn_line,
)
from src.en.dashboard import TEAM_GEAR  # noqa: E402

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

# Slot frame colours measured off the stuck Equipment screen, as (red, green, blue), left to right per
# combatant. Each row holds exactly one Mythic, which is why the client refused every click of that run.
MEASURED_ROWS = (((60, 75, 135), (159, 87, 69), (137, 82, 164)),
                 ((22, 17, 24), (139, 83, 163), (25, 20, 26)),
                 ((13, 15, 16), (12, 14, 15), (138, 83, 164)))
# The same screen with the client's refusal toast drawn over the top row, which dims its slots.
DIMMED_ROW = ((22, 24, 30), (52, 45, 43), (137, 82, 164))
# The colour compare the helpers reach for. Upstream's own, so its tolerance is the one being tested.
RGB = types.SimpleNamespace(_rgb_is_close=lambda rgb, target, tolerance=30:
                            rgb is not None and all(abs(a - b) <= tolerance for a, b in zip(rgb, target)))
# The Combatants screen behind the user's report, read left to right: Arabella wears one of each, and the two
# beside her wear a Mythic and nothing else. The Equipment row called all nine of these slots empty.
TEAM_COLOURS = (((60, 75, 135), (160, 88, 69), (136, 82, 164)),
                ((15, 15, 15), (136, 82, 164), (20, 18, 18)),
                ((20, 18, 19), (19, 18, 17), (136, 82, 164)))
TEAM_NAMES = ("Arabella", "Adelheid", "Narja")
# The two taps upstream's capture makes: the tab it reads, then the corner that shuts the page. Upstream's own
# numbers, from `handle_archive_target_member`.
COMBATANTS_TAB = (0.201, 0.056)
CLOSE_TAP = (0.960, 0.054)
# Upstream's own quality buckets, keyed by the colour it reads them off. Its top bucket takes everything it
# cannot place, which is the behaviour the tier naming has to see to be tested at all.
BUCKETS = {(15, 15, 15): "", (61, 76, 138): "普通", (160, 88, 69): "史诗"}
# The colour each bucket is read off, which is `BUCKETS` the other way round plus the violet upstream has no
# name for and drops into its top bucket.
BUCKET_COLOURS = {bucket: rgb for rgb, bucket in BUCKETS.items()} | {TOP_QUALITY: (136, 82, 164)}
# A piece the install screen is offering, as `_equipment_info` reports it. Epic is upstream's bucket for what
# this client calls Legend.
OFFERED = {"name": "Corroded Gauntlets", "slot": 2, "quality": "史诗", "rank": None}


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


def team_utils(colours=TEAM_COLOURS, names=TEAM_NAMES):
    """Build a `utils` stand-in for the Combatants screen, reading colours the way upstream does.

    Args:
        colours: The frame colour of each combatant's three slots, or None for a frame that gave nothing.
        names: The name read above each column, blank where it could not be read.

    Returns:
        The stand-in namespace. Setting `open` to False on it is the page being tapped closed: the names stay
        readable, because the capture holds its OCR pass, and the pixels stop, because the frame does not.
    """
    by_name_x = dict(zip((0.159, 0.432, 0.705), names))
    points = {point: colours[column][slot]
              for column in range(3) if colours
              for slot, point in enumerate(combatant_slot_points(column))}

    def quality_at(task_, point, allow_empty=False):
        rgb = points.get(point)
        bucket = next((name for target, name in BUCKETS.items() if RGB._rgb_is_close(rgb, target)), None)
        return (bucket if bucket is not None else "传说"), rgb

    utils = types.SimpleNamespace(
        find_box_at_point=lambda task_, x, y: FakeBox(by_name_x.get(round(x, 3), "") if utils.open else "", 0, 0),
        _equipment_quality_at=lambda task_, point, allow_empty=False: quality_at(task_, point, allow_empty)
        if utils.open else ("", None),
        _rgb_is_close=RGB._rgb_is_close,
        _move_and_click=lambda task_, x, y: None,
        open=True)
    return utils


def mythic_screen():
    """Build the Equipment screen with a Mythic piece on offer.

    Returns:
        A `FakeTask`.
    """
    return FakeTask(level_tags() + [FakeBox(MYTHIC_CAPTION, CAPTION_X, CAPTION_Y)])


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
        """Build a stand-in for the `utils` module carrying only the seams this patch moves.

        Returns:
            A namespace with `_find_member_level_tags` and `random`.
        """
        return types.SimpleNamespace(
            _find_member_level_tags=lambda task_, *args, **kwargs: level_tags(),
            _find_target_member_index=lambda task_, *args, **kwargs: None,
            _should_install_equipment=lambda task_, name, quality, new: (True, "品质普通高于未安装"),
            random=random,
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

    def test_gear_the_target_passes_on_goes_to_the_recommended_row(self):
        # Chaos binds to the save-data combatant by avatar, not by position, and hands what it turns down to a
        # `random.choice` of the others. A run saw the banner on row 3 and still left the pick to chance.
        target = TAG_Y[1]
        for recommended, expected in ((0, {TAG_Y[0]}), (2, {TAG_Y[2]}), (1, {TAG_Y[0], TAG_Y[2]}), (None, {TAG_Y[0], TAG_Y[2]})):
            with self.subTest(recommended=recommended):
                utils = self.utils_stub()
                picked = []

                def handler(task_):
                    others = [box for box in utils._find_member_level_tags(task_) if box.y + box.height / 2 != target]
                    picked.append(round(utils.random.choice(others).y + 15))
                    return False

                for _ in range(10):
                    preferring_recommended(handler, utils)(equipment_screen(recommended=recommended))
                self.assertLessEqual(set(picked), expected)
                self.assertIs(random, utils.random)

class TestStandingDownForTheRecommended(unittest.TestCase):
    """Who an ordinary piece goes to when the client is recommending somebody.

    Upstream asks the save-data combatant first and only offers the rest what it turns down, so a piece it
    could use never reached the banner - a run installed a ring on it while the client recommended another
    combatant. A piece the user's priority list does not name now goes to the banner's row instead.
    """

    def stub(self, bound=2, install=(True, "品质普通高于未安装")):
        """Build a `utils` stand-in for the install screen.

        Args:
            bound: The row upstream binds the save-data combatant to, counted after the reorder, or None.
            install: What upstream's own comparison decides.

        Returns:
            The stand-in namespace.
        """
        return types.SimpleNamespace(
            _find_member_level_tags=lambda task_, *args, **kwargs: level_tags(),
            _find_target_member_index=lambda task_, *args, **kwargs: bound,
            _should_install_equipment=lambda task_, name, quality, new: install,
            random=random,
        )

    def decide(self, task, rank=None, **stub):
        """Run the wrapped handler and report the decision upstream was handed.

        Args:
            task: The Equipment screen to run against.
            rank: The piece's place in the user's priority list, or None when it names no such piece.
            **stub: Passed to `stub`.

        Returns:
            The `(install, reason)` pair.
        """
        utils = self.stub(**stub)
        reached = []

        def handler(task_):
            utils._find_member_level_tags(task_, (0.6, 0.3, 0.7, 0.8), page="安装装备页面")
            utils._find_target_member_index(task_, [], (0.6, 0.2, 0.7, 0.9))
            reached.append(utils._should_install_equipment(task_, "", "", {"rank": rank, "quality": "普通"}))
            return False

        preferring_recommended(handler, utils)(task)
        return reached[0]

    def chaos(self, recommended=2):
        """Build a Chaos install screen, which is the mode that binds a save-data combatant.

        Args:
            recommended: The row carrying the banner, or None for no banner.

        Returns:
            A `FakeTask`.
        """
        task = equipment_screen(recommended=recommended)
        task.default_config = {"刷存档主战员": "Arabella"}
        return task

    def test_the_save_data_combatant_stands_down_for_an_unnamed_piece(self):
        install, reason = self.decide(self.chaos())
        self.assertFalse(install)
        self.assertIn("recommends", reason)

    def test_a_piece_the_priority_list_names_still_goes_to_it(self):
        self.assertEqual((True, "品质普通高于未安装"), self.decide(self.chaos(), rank=0))

    def test_nothing_changes_when_the_banner_is_on_the_save_data_combatant(self):
        # The reorder puts the banner's row first, so a save-data combatant bound there is the banner's own.
        self.assertEqual((True, "品质普通高于未安装"), self.decide(self.chaos(), bound=0))

    def test_nothing_changes_without_a_banner(self):
        self.assertEqual((True, "品质普通高于未安装"), self.decide(self.chaos(recommended=None)))

    def test_nothing_changes_when_the_save_data_combatant_was_not_found(self):
        # Upstream gives the piece away by itself then, and the fallback is already the banner's row.
        self.assertEqual((True, "品质普通高于未安装"), self.decide(self.chaos(), bound=None))

    def test_a_refusal_is_left_as_it_was(self):
        self.assertEqual((False, "当前装备配置优先级更高"),
                         self.decide(self.chaos(), install=(False, "当前装备配置优先级更高")))

    def test_sortie_is_left_alone(self):
        # It binds no save-data combatant, so the banner's row is already the one upstream prefers.
        task = equipment_screen(recommended=2)
        task.default_config = {}
        self.assertEqual((True, "品质普通高于未安装"), self.decide(task))

    def test_a_mythic_is_left_on_its_own_path(self):
        # Its banner row may have been dropped for having no room, and standing down would then extract it.
        task = self.chaos()
        task.all_texts = task.all_texts + [FakeBox(MYTHIC_CAPTION, CAPTION_X, CAPTION_Y)]
        self.assertEqual((True, "品质普通高于未安装"), self.decide(task))


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

    def test_overrides_a_refusal_from_the_priority_list(self):
        installed, reason = self.decide(mythic_screen(), (False, "当前装备配置优先级更高"), "史诗")
        self.assertTrue(installed)
        self.assertIn("Mythic", reason)

    def test_leaves_an_acceptance_alone(self):
        self.assertEqual((True, "配置优先级更高"),
                         self.decide(mythic_screen(), (True, "配置优先级更高"), "史诗"))

    def test_does_not_swap_one_mythic_for_another(self):
        # The slot already holds the best thing there is, so replacing it gains nothing.
        self.assertEqual((False, "品质传说不高于传说"),
                         self.decide(mythic_screen(), (False, "品质传说不高于传说"), TOP_QUALITY))

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
    """Reading every combatant's slots off the screen that shows all three, and saying what they wear.

    The Equipment row used to change only where a run read the Combatants screen, which is once a run. A log
    of one run shows the cost: a piece handed to the third combatant at 23:00:37, and the row still reading
    `Rare/Rare/Legend, Rare/-/-, Rare/-/-` on every frame after it.
    """

    def stubs(self, rows=3, worn=("", TOP_QUALITY, ""), colours=None, piece=None):
        """Build a `utils` stand-in for the install screen.

        Args:
            rows: How many combatant rows the screen shows.
            worn: The bucket each of a row's three slots reads as, the same for every row.
            colours: The colour each of those slots is framed in, or None to use the colour its bucket is
                read off. Given to place a colour upstream drops into its top bucket without naming.
            piece: The piece the screen is offering, or None when the handler reads none.

        Returns:
            A `(utils, seen)` pair, where `seen` records which rows were read for their slots.
        """
        seen = []

        def find_tags(task_, region, page=None):
            return level_tags()[:rows]

        def qualities(task_, row):
            # Upstream probes each slot in turn, which is the read the colours are captured through.
            seen.append(row)
            return [utils._equipment_quality_at(task_, (row, slot), allow_empty=True)[0] for slot in range(3)]

        def quality_at(task_, point, allow_empty=False):
            slot = point[1]
            return worn[slot], colours[slot] if colours else BUCKET_COLOURS[worn[slot]]

        utils = types.SimpleNamespace(_find_member_level_tags=find_tags, _member_equipment_qualities=qualities,
                                      _equipment_quality_at=quality_at, _rgb_is_close=RGB._rgb_is_close,
                                      _equipment_info=lambda task_, *regions: piece,
                                      _move_and_click=lambda task_, x, y: None)
        return utils, seen

    def handler(self, utils, handed_to=None):
        """Build a stand-in for upstream, which reads the rows and may hand the piece to one of them.

        Args:
            utils: The stand-in the handler reads and taps through.
            handed_to: The row the piece is handed to, or None for a handler that hands nothing over.

        Returns:
            The handler.
        """
        def handle(task_):
            rows = utils._find_member_level_tags(task_, (0.6, 0.3, 0.7, 0.8), page="安装装备页面")
            utils._equipment_info(task_, (0.1, 0.2, 0.3, 0.4), (0.1, 0.2, 0.3, 0.4), (0.1, 0.2, 0.3, 0.4))
            if handed_to is not None:
                chosen = rows[handed_to]
                utils._move_and_click(task_, HANDOVER_X, (chosen.y + chosen.height / 2) / task_.height)
            return True

        handle.__name__ = "handle_equipment"
        return handle

    def worn(self, task=None, handed_to=None, **stubs):
        """Run the wrapped handler and report what the Equipment row was left holding.

        Args:
            task: The task to run against, or None for a screen carrying no caption.
            handed_to: The row the piece is handed to, or None for a handler that hands nothing over.
            **stubs: Passed to `stubs`.

        Returns:
            The row's text, or None when nothing was written.
        """
        utils, _ = self.stubs(**stubs)
        task = FakeTask([]) if task is None else task
        remembering_slots(self.handler(utils, handed_to=handed_to), utils)(task)
        return getattr(task, TEAM_GEAR, None)

    def test_every_row_is_read(self):
        utils, seen = self.stubs()
        task = FakeTask([])
        remembering_slots(self.handler(utils), utils)(task)
        self.assertEqual(list(TAG_Y), [round(row.y + row.height / 2) for row in seen])
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

    def test_the_row_says_what_the_screen_shows(self):
        self.assertEqual("-/Mythic/-, -/Mythic/-, -/Mythic/-", self.worn())

    def test_the_piece_handed_over_is_written_into_the_row_that_took_it(self):
        # The slots are read before the client has drawn the new piece, so the screen alone reports the third
        # combatant's slot as empty and the row sits a piece behind for the rest of the run.
        self.assertEqual("-/Mythic/-, -/Mythic/-, -/Mythic/Legend", self.worn(piece=OFFERED, handed_to=2))

    def test_a_mythic_handed_over_is_named_rather_than_left_unplaced(self):
        # Upstream's top bucket holds every colour it could not place as well, so the caption decides.
        self.assertEqual("-/Mythic/-, -/Mythic/Mythic, -/Mythic/-",
                         self.worn(task=mythic_screen(), piece=dict(OFFERED, quality=TOP_QUALITY), handed_to=1))

    def test_a_screen_that_gave_nothing_leaves_the_row_alone(self):
        # Nine unknowns are worth less than the reading the row already had.
        self.assertIsNone(self.worn(worn=(TOP_QUALITY,) * 3, colours=(DIMMED_ROW[0],) * 3))


class TestBuyingOnSpree(unittest.TestCase):
    """What a generated equipment list may offer the shop.

    Only on a spree - opened at `SPREE_START`, held for the visit until `SPREE_END` - and only for a slot empty on
    somebody. A configured list never reaches the builder, so it is not gated here at all.
    """

    def builder(self, credit, slots=None, listed=("Crimson Sword",)):
        """Build a task and a gated list builder that offers `listed` for every equipment key.

        Args:
            credit: What the run is holding. `self.credit` can be changed between calls to spend it.
            slots: What was last seen of each combatant's slots, or None for a screen never seen.
            listed: What the ungated builder generates.

        Returns:
            A `(task, offered)` pair, where `offered(slot)` is what the gated builder hands back for that slot.
        """
        task = FakeTask([])
        task.start_time, task.node_status = 1.0, {"pass_final_boss_count": 0, "node_count": 4}
        if slots is not None:
            setattr(task, SLOTS, slots)
        self.credit = credit
        utils = types.SimpleNamespace(_get_current_credit=lambda task_: self.credit)
        generated = buying_on_spree(lambda task_, key, farmed="": list(listed), lambda: utils)
        keys = {slot: key for key, slot in EQUIPMENT_KEYS.items()}
        return task, lambda slot: generated(task, keys[slot])

    def test_a_rich_run_fills_a_bare_slot_and_leaves_filled_ones(self):
        task, offered = self.builder(SPREE_START, slots=[["", "传说", "传说"]])
        self.assertEqual([["Crimson Sword"], [], []], [offered(slot) for slot in range(3)])

    def test_a_spree_holds_below_the_start_and_ends_at_the_end(self):
        task, offered = self.builder(SPREE_START)
        for credit, expected in ((SPREE_START - 1, []), (SPREE_START, ["Crimson Sword"]),
                                 (SPREE_END + 1, ["Crimson Sword"]), (SPREE_END, []), (SPREE_END + 1, [])):
            with self.subTest(credit=credit):
                self.credit = credit
                self.assertEqual(expected, offered(0))

    def test_a_spree_ends_with_the_shop_visit(self):
        task, offered = self.builder(SPREE_START)
        offered(0)
        task.node_status["node_count"] += 1
        self.credit = SPREE_START - 1
        self.assertEqual([], offered(0))

    def test_other_lists_and_empty_lists_pass_through(self):
        task, _ = self.builder(0)
        generated = buying_on_spree(lambda task_, key, farmed="": ["Shock"], lambda: None)
        self.assertEqual(["Shock"], generated(task, "卡牌奖励优先级"))
        task, offered = self.builder(0, listed=())
        self.assertEqual([], offered(0))


class TestMythicColour(unittest.TestCase):
    """Telling a Mythic slot from every other slot by its frame colour."""

    def test_every_measured_mythic_reads_as_one(self):
        for rgb in ((137, 82, 164), (139, 83, 163), (138, 83, 164), (136, 96, 184)):
            with self.subTest(rgb=rgb):
                self.assertTrue(is_mythic_colour(RGB, rgb))

    def test_nothing_else_on_the_screen_does(self):
        # Normal, Epic, empty, and the dimmed pair a toast leaves behind. Upstream reads the last three as
        # Mythic, because its colour read names Normal and Epic and hands everything else to the top bucket.
        for rgb in ((60, 75, 135), (159, 87, 69), (13, 15, 16), (22, 24, 30), (52, 45, 43)):
            with self.subTest(rgb=rgb):
                self.assertFalse(is_mythic_colour(RGB, rgb))

    def test_a_slot_that_could_not_be_read_is_not_one(self):
        self.assertFalse(is_mythic_colour(RGB, None))


class TestRoomForMythic(unittest.TestCase):
    """Whether a combatant could legally take the Mythic on offer."""

    def test_a_mythic_in_another_slot_leaves_no_room(self):
        self.assertFalse(has_room_for_mythic(RGB, MEASURED_ROWS[0], 0))

    def test_a_mythic_in_the_same_slot_is_only_a_swap(self):
        self.assertTrue(has_room_for_mythic(RGB, MEASURED_ROWS[0], 2))

    def test_a_combatant_wearing_none_has_room(self):
        self.assertTrue(has_room_for_mythic(RGB, ((60, 75, 135), (159, 87, 69), (13, 15, 16)), 0))

    def test_a_dimmed_row_is_blocked_only_by_its_real_mythic(self):
        # Its other two slots hold a toast-dimmed Epic and a toast-dimmed empty, which upstream's bucket calls
        # Mythic. Reading them as such would extract a piece this combatant could simply have swapped.
        self.assertTrue(has_room_for_mythic(RGB, DIMMED_ROW, 2))
        self.assertFalse(has_room_for_mythic(RGB, DIMMED_ROW, 0))

    def test_a_slot_that_could_not_be_read_does_not_block(self):
        self.assertTrue(has_room_for_mythic(RGB, (None, None, None), 0))


class TestOfferingMythicWhereItFits(unittest.TestCase):
    """Which combatants a Mythic piece is offered to.

    The client allows one Mythic per combatant. Upstream checks that for the combatant it is about to equip and
    then hands what that one turns down to another without checking it, so a run offered a Mythic to combatants
    already wearing one and clicked each in turn for as long as it was on screen, refused every time.
    """

    def utils_stub(self, rows=MEASURED_ROWS, slot=0):
        """Build a `utils` stand-in for the install screen, reading colours the way upstream does.

        Args:
            rows: The frame colour of each combatant's three slots.
            slot: The slot the piece on offer belongs in, or None for a piece that could not be read.

        Returns:
            The stand-in namespace.
        """
        colours = {f"row{index}": row for index, row in enumerate(rows)}

        def quality_at(task_, point, allow_empty=False):
            return "", colours[point[0]][point[1]]

        def qualities(task_, row):
            return [utils._equipment_quality_at(task_, (row, index), allow_empty=True)[0] for index in range(3)]

        utils = types.SimpleNamespace(
            _equipment_info=lambda task_, *regions: {"slot": slot} if slot is not None else None,
            _find_member_level_tags=lambda task_, *args, **kwargs: list(colours),
            _member_equipment_qualities=qualities,
            _equipment_quality_at=quality_at,
            _rgb_is_close=RGB._rgb_is_close,
        )
        return utils

    def rows_seen(self, task, **stub):
        """Run the wrapped handler and report the combatant rows it was handed.

        Args:
            task: The Equipment screen to run against.
            **stub: Passed to `utils_stub`.

        Returns:
            The rows upstream saw.
        """
        utils = self.utils_stub(**stub)
        seen = []

        def handler(task_):
            utils._equipment_info(task_, (0.2, 0.3, 0.4, 0.5))
            seen.append(utils._find_member_level_tags(task_, (0.6, 0.3, 0.7, 0.8), page="安装装备页面"))
            return False

        offering_mythic_where_it_fits(handler, utils)(task)
        return seen[0]

    def test_a_team_all_wearing_one_is_offered_nobody(self):
        # Which is the hang: every click refused, the screen unchanged, the handler run again a second later.
        self.assertEqual([], self.rows_seen(mythic_screen()))

    def test_only_the_combatants_with_room_are_offered_it(self):
        # The banner picks one row for upstream, so leaving a blocked row in is enough to hang on its own.
        rows = (MEASURED_ROWS[0], ((13, 15, 16),) * 3, MEASURED_ROWS[2])
        self.assertEqual(["row1"], self.rows_seen(mythic_screen(), rows=rows))

    def test_a_combatant_wearing_one_in_that_very_slot_keeps_its_place(self):
        # Rows 1 and 3 wear their Mythic in slot 3, so taking this one is a swap and leaves them wearing one.
        # Row 2 wears its own in slot 2, which the piece would not replace, so it drops out.
        self.assertEqual(["row0", "row2"], self.rows_seen(mythic_screen(), slot=2))

    def test_an_ordinary_piece_is_left_alone(self):
        self.assertEqual(["row0", "row1", "row2"], self.rows_seen(equipment_screen()))

    def test_a_piece_whose_slot_could_not_be_read_is_left_alone(self):
        self.assertEqual(["row0", "row1", "row2"], self.rows_seen(mythic_screen(), slot=None))


class TestPlacementReadsTheWholeScreen(unittest.TestCase):
    """The order the two row readers are installed in, which nothing else would notice breaking.

    `offering_mythic_where_it_fits` and `remembering_slots` both stand in for `_find_member_level_tags`. The
    rows the first drops must still reach the second, or the slot record `bare_slots` and the shop spree read
    goes stale exactly while a Mythic is on screen. `install` is what orders them, so it is what is run here.
    """

    def utils_stub(self):
        """Build a `utils` stand-in whose combatants all already wear a Mythic.

        Returns:
            A `(utils, seen)` pair, where `seen` holds the rows upstream was shown.
        """
        seen = []
        colours = dict(zip(("row0", "row1", "row2"), MEASURED_ROWS))

        def upstream(task_):
            utils._equipment_info(task_, (0.2, 0.3, 0.4, 0.5))
            seen.append(utils._find_member_level_tags(task_, (0.6, 0.3, 0.7, 0.8), page="安装装备页面"))
            return True

        upstream.__name__ = "handle_equipment"

        def quality_at(task_, point, allow_empty=False):
            rgb = colours[point[0]][point[1]]
            return ("传说" if RGB._rgb_is_close(rgb, (137, 82, 164)) else ""), rgb

        utils = types.SimpleNamespace(
            handle_equipment=upstream,
            _equipment_info=lambda task_, *regions: {"slot": 0},
            _find_member_level_tags=lambda task_, *args, **kwargs: list(colours),
            _member_equipment_qualities=lambda task_, row: [
                utils._equipment_quality_at(task_, (row, index), allow_empty=True)[0] for index in range(3)],
            _equipment_quality_at=quality_at,
            _rgb_is_close=RGB._rgb_is_close,
            _find_target_member_index=lambda task_, *args, **kwargs: None,
            _should_install_equipment=lambda *args: (False, ""),
            _move_and_click=lambda task_, x, y: None,
            random=random,
        )
        return utils, seen

    def test_upstream_is_shown_nobody_while_every_row_is_still_recorded(self):
        utils, seen = self.utils_stub()
        install(utils)
        task = FakeTask([FakeBox(MYTHIC_CAPTION, CAPTION_X, CAPTION_Y)] + level_tags())
        utils.handle_equipment(task)
        self.assertEqual([[]], seen)
        self.assertEqual(3, len(getattr(task, SLOTS)))



class TestSlotTier(unittest.TestCase):
    """Naming the tier a slot holds.

    Upstream's own names are a tier out on this client. Thirteen pieces the logs name, checked against the
    client's rarity table, put RARE behind the bucket it calls Normal, LEGEND behind Epic, and UNIQUE - the
    Mythic the client allows one of - behind Legend.
    """

    def tier(self, rgb):
        """Name the tier a slot drawn in one colour holds.

        Args:
            rgb: The colour the slot's frame is drawn in, or None for a slot that could not be read.

        Returns:
            The tier's name.
        """
        colours = ((rgb, rgb, rgb),) * 3
        return slot_tier(FakeTask([]), team_utils(colours=colours), combatant_slot_points(0)[0])

    def test_each_measured_colour_names_its_tier(self):
        for rgb, expected in (((15, 15, 15), "-"), ((60, 75, 135), "Rare"),
                              ((160, 88, 69), "Legend"), ((136, 82, 164), MYTHIC_TIER)):
            with self.subTest(rgb=rgb):
                self.assertEqual(expected, self.tier(rgb))

    def test_a_colour_upstream_cannot_place_is_not_quietly_called_mythic(self):
        # Upstream hands every such colour to its top bucket, which is why a toast-dimmed slot read as the
        # rarest thing in the game. Only the violet itself earns that name here.
        self.assertEqual(UNKNOWN_TIER, self.tier((120, 200, 40)))

    def test_a_slot_that_could_not_be_read_is_unknown(self):
        self.assertEqual(UNKNOWN_TIER, self.tier(None))


class TestTeamEquipment(unittest.TestCase):
    """Reading all nine slots off the Combatants screen."""

    def test_the_screen_the_row_got_wrong_now_reads_true(self):
        self.assertEqual("Rare/Legend/Mythic, -/Mythic/-, -/-/Mythic",
                         worn_line(team_equipment(FakeTask([]), team_utils())))

    def test_a_column_that_could_not_be_read_keeps_its_place(self):
        # The row carries no names, so which combatant a line belongs to is which place it is in. A column
        # dropped for being unreadable would hand the next one's gear to the combatant before it.
        colours = (TEAM_COLOURS[0], (None, None, None), TEAM_COLOURS[2])
        self.assertEqual("Rare/Legend/Mythic, ?/?/?, -/-/Mythic",
                         worn_line(team_equipment(FakeTask([]), team_utils(colours=colours))))

    def test_a_frame_that_gave_nothing_reports_nothing(self):
        # An unreadable frame must leave the row saying what it said, not overwrite it with nine unknowns.
        self.assertEqual("", worn_line(team_equipment(FakeTask([]), team_utils(colours=None, names=("", "", "")))))


class TestReadingTheTeamGear(unittest.TestCase):
    """When the team's gear is read, which is the whole of whether it reads anything.

    Upstream's capture taps the page closed and sleeps a second before it returns. `all_texts` survives that
    and `frame` does not, so a read afterwards got the names off the held OCR pass and the pixels off whatever
    the client had drawn since - a run reported "Arabella -/-/-, Narja ?/?/?" for a team plainly
    wearing gear. The read rides the capture's own taps so it lands while the page is still up.
    """

    def capture(self, utils, taps=(COMBATANTS_TAB, CLOSE_TAP)):
        """Stand in for upstream's capture: it taps the tab, reads its names, then taps the page shut.

        Args:
            utils: The stand-in the capture taps and reads through.
            taps: The taps it makes, in order.

        Returns:
            The handler.
        """
        def handle_archive_target_member(task):
            for x, y in taps:
                utils._move_and_click(task, x, y)
                if (x, y) == CLOSE_TAP:
                    # What closing costs: the frame moves on, the held OCR pass does not.
                    utils.open = False
            return True

        return handle_archive_target_member

    def read(self, utils, **capture):
        """Run the wrapped capture and report what the row was left holding.

        Args:
            utils: The stand-in to run against.
            **capture: Passed to `capture`.

        Returns:
            The row's text, or None when nothing was read.
        """
        task = FakeTask([])
        reading_the_team_gear(self.capture(utils, **capture), utils, utils)(task)
        return getattr(task, TEAM_GEAR, None)

    def test_the_gear_is_read_while_the_page_is_still_open(self):
        self.assertEqual("Rare/Legend/Mythic, -/Mythic/-, -/-/Mythic", self.read(team_utils()))

    def test_reading_after_the_page_shuts_is_what_this_prevents(self):
        # The same stand-in read with the page already shut, which is the row the run actually reported.
        utils = team_utils()
        utils.open = False
        self.assertEqual("-/-/-, -/-/-, -/-/-", worn_line(team_equipment(FakeTask([]), utils)))

    def test_the_tab_tap_is_too_early_to_read_on(self):
        # It happens before the capture's own OCR, so the names are not all up yet and the read waits.
        utils = team_utils(names=("", "", ""))
        self.assertIsNone(self.read(utils, taps=(COMBATANTS_TAB,)))

    def test_the_read_happens_once_however_many_taps_follow(self):
        utils = team_utils()
        task = FakeTask([])
        reading_the_team_gear(self.capture(utils, taps=(CLOSE_TAP, CLOSE_TAP)), utils, utils)(task)
        self.assertEqual("Rare/Legend/Mythic, -/Mythic/-, -/-/Mythic", getattr(task, TEAM_GEAR))

    def test_a_capture_that_never_shows_its_names_leaves_what_was_known(self):
        utils = team_utils(names=("", "", ""))
        task = FakeTask([])
        setattr(task, TEAM_GEAR, "Rare/Legend/Mythic, -/Mythic/-, -/-/Mythic")
        reading_the_team_gear(self.capture(utils), utils, utils)(task)
        self.assertEqual("Rare/Legend/Mythic, -/Mythic/-, -/-/Mythic", getattr(task, TEAM_GEAR))
