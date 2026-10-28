"""Check that a run starting on the Combatants tab reads it instead of tapping its way back to it, that Sortie goes there once a run, and
that the deck read off All Piles on the way values each card by its Epiphany, and that a Sortie Epiphany goes on the card that read found without one."""

import sys
import types
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import cards, epiphany, navigation, piles, rewards  # noqa: E402
from src.en.handlers import standing_in  # noqa: E402
from src.en.battle import PARTY  # noqa: E402
from src.en.game_text import DESCRIPTIONS, EPIPHANIES  # noqa: E402
from tests.fakes import HEIGHT, WIDTH, FakeBox  # noqa: E402

TARGET = "Arabella"
# What the log shows on the Combatants tab, at the three points upstream reads names from.
ON_THE_TAB = {(0.159, 0.368): "Arabella", (0.432, 0.368): "Veronica", (0.705, 0.369): "Mika"}
# A sibling tab: names at the same points, none of them a combatant.
ANOTHER_TAB = {(0.159, 0.368): "Whisper", (0.432, 0.368): "Ember", (0.705, 0.369): "Tallow"}
# The taps upstream's capture makes: the 3-person icon, the Combatants tab, then the one that closes the page.
CLOSE_PAGE = (0.960, 0.054)
# Columns one and four of an All Piles page as the reader returned them, as (text, centre x, centre y, width, height) in pixels. The two
# Experienced Strikes carry different versions, Hew's text names a card, and the last row runs off the bottom.
PILES_PAGE = (
    ("Slash", 707, 159, 70, 28), ("XBasic Attack", 756, 184, 164, 26), ("143% Defense-Based", 749, 364, 214, 26), ("Damage", 749, 392, 96, 30),
    ("Increase Damage", 747, 417, 178, 28), ("Amount of Exhaust", 749, 443, 186, 20), ("cards by 15% for1 turn", 751, 468, 234, 30),
    ("(max2 stacks)", 748, 494, 148, 28),
    ("Experienced Strike", 773, 612, 218, 31), ("XAttack", 723, 640, 110, 33), ("168% Defense-Based", 750, 817, 216, 26), ("Damage", 751, 846, 88, 29),
    ("20% DMG-Based Shield", 756, 869, 248, 30), ("Increase Damage", 748, 895, 176, 24), ("Amount of Exhaust", 749, 920, 190, 26),
    ("cards by 20% for 1 turn", 752, 948, 232, 26),
    ("QVulture Ejection", 748, 1060, 240, 37),
    ("Hew", 1647, 158, 62, 30), ("Attack", 1690, 187, 68, 20), ("[Unique/lnitiation/", 1706, 364, 212, 26), ("Exhaust / Ephemeral]", 1701, 391, 222, 32),
    ("420% Defense-Based", 1701, 416, 222, 26), ("Damage", 1701, 444, 90, 27), ("Incinerate: Create", 1702, 468, 176, 19), ("1HewLv.1", 1704, 495, 112, 26),
    ("Experienced Strike", 1727, 612, 210, 25), ("Attack", 1676, 640, 108, 33), ("252%Defense-Based", 1699, 818, 214, 20), ("Damage", 1702, 846, 90, 29),
    ("20% DMG-Based Shield", 1707, 869, 250, 30), ("Increase Shield Gain", 1701, 895, 202, 20), ("Amount of Skill Cards", 1700, 921, 212, 20),
    ("by 30%for1turn", 1704, 947, 172, 20),
    ("Absolute Protection", 1725, 1062, 214, 32),
    # A card named inside another card's text, with a text line as close below it as a type label would be. From the next page.
    ("Contaminated Spore", 1282, 433, 210, 30), ("Retain:Create", 1316, 465, 146, 19),
)
# The Experienced Strike Epiphany the second copy above carries.
SHIELD_GAIN = next(text for text in EPIPHANIES["Experienced Strike"] if "Shield Gain" in text)


class FakeTask:
    """A mode recording the taps a handler asks for."""

    def __init__(self):
        self.clicks = []
        self.boxes = []

    def click_box(self, box, *args, **kwargs):
        self.boxes.append(getattr(box, "name", box))


def install(names, target=TARGET):
    """Put stand-in task modules where `handlers.loaded` will find them.

    Args:
        names: What OCR reads at each of the three name points.
        target: The combatant the run is farming, as the setting would give it.

    Returns:
        The stand-in `utils_chaos`, whose `_move_and_click` the capture calls.
    """
    utils = types.ModuleType("utils")
    utils.find_box_at_point = lambda task, x, y: (
        types.SimpleNamespace(name=names[(x, y)]) if (x, y) in names else None
    )
    utils._get_config_value = lambda task, key, default=None: target

    utils_chaos = types.ModuleType("utils_chaos")
    utils_chaos._move_and_click = lambda task, x, y: task.clicks.append((x, y))

    sys.modules["utils"] = utils
    sys.modules["utils_chaos"] = utils_chaos
    return utils_chaos


def upstream_capture(utils_chaos, extra_boxes=0):
    """Stand in for upstream's capture: the two navigation taps, then the tap that closes the page.

    Args:
        utils_chaos: The module whose `_move_and_click` the capture reaches for.
        extra_boxes: Box clicks beyond the one upstream makes today, for the rebase the tally guards against.

    Returns:
        A handler that records what it tapped and reports that it handled the frame.
    """
    def handle_archive_target_member(task):
        for _ in range(1 + extra_boxes):
            task.click_box(types.SimpleNamespace(name="memberinfo"))
        utils_chaos._move_and_click(task, *navigation.COMBATANTS_TAB)
        utils_chaos._move_and_click(task, *CLOSE_PAGE)
        return True

    return handle_archive_target_member


class TestOnCombatantsTab(unittest.TestCase):
    """The guard that decides whether the trip can be skipped."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def test_a_combatant_on_screen_proves_the_tab_is_open(self):
        install(ON_THE_TAB)
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_sibling_tab_is_not_mistaken_for_it(self):
        """Partners and Fate draw names at the same points, so names alone would not be proof."""
        install(ANOTHER_TAB)
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))

    def test_a_screen_with_no_names_is_not_it(self):
        install({})
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))

    def test_one_readable_slot_is_enough(self):
        install({(0.705, 0.369): TARGET})
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_name_read_with_extra_text_still_counts(self):
        """Upstream matches either way round, so anything its own read would accept has to be accepted here."""
        install({(0.159, 0.368): "Arabella Lv40"})
        self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_it_does_not_depend_on_who_is_farmed(self):
        # A run farming nobody clicked the icon and the tab every time, because the farmed name was the only proof.
        for target in ("", "(none)", "Heidemarie"):
            with self.subTest(target=target):
                install(ON_THE_TAB, target=target)
                self.assertTrue(navigation.on_combatants_tab(FakeTask()))

    def test_a_short_name_inside_a_longer_word_does_not_count(self):
        install({(0.159, 0.368): "Fenia"})
        self.assertFalse(navigation.on_combatants_tab(FakeTask()))


class TestReadingInPlace(unittest.TestCase):
    """The wrapper drops the two navigation taps and leaves everything else upstream does alone."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def capture(self, names, extra_boxes=0):
        """Run the wrapped capture against a screen.

        Args:
            names: What OCR reads at the three name points.
            extra_boxes: Box clicks beyond the one upstream makes today.

        Returns:
            A `(task, handled)` pair.
        """
        utils_chaos = install(names)
        task = FakeTask()
        handled = navigation.reading_in_place(upstream_capture(utils_chaos, extra_boxes))(task)
        return task, handled

    def test_only_the_trip_back_to_the_screen_is_dropped(self):
        """Both navigation taps go, the tap that closes the page stays, and the answer is handed back."""
        task, handled = self.capture(ON_THE_TAB)
        self.assertEqual([], task.boxes)
        self.assertEqual([CLOSE_PAGE], task.clicks)
        self.assertTrue(handled)

    def test_a_run_starting_elsewhere_taps_only_the_icon(self):
        """The 3-person icon already lands on the Combatants tab, so the tab tap after it would do nothing."""
        task, handled = self.capture(ANOTHER_TAB)
        self.assertEqual(["memberinfo"], task.boxes)
        self.assertEqual([CLOSE_PAGE], task.clicks)
        self.assertTrue(handled)

    def test_a_capture_that_throws_still_puts_them_back(self):
        """A capture that raised while the taps were stood in for would leave upstream permanently rewired."""
        utils_chaos = install(ON_THE_TAB)
        original = utils_chaos._move_and_click
        task = FakeTask()

        def raising(task):
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            navigation.reading_in_place(raising)(task)
        self.assertIs(original, utils_chaos._move_and_click)
        self.assertNotIn("click_box", task.__dict__)

    def test_the_stand_in_keeps_the_name_upstream_logs(self):
        """`_move_and_click` logs the name of the frame that called it, and this stands in mid-capture."""
        stand_in = navigation.without_the_tab_tap(lambda task, x, y: None, navigation.Dropped())
        self.assertEqual("handle_archive_target_member", stand_in.__code__.co_name)


class TestTheTallyNoticesARebase(unittest.TestCase):
    """Both taps are recognised by shape, so upstream moving one has to be made loud rather than silent."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def warnings(self, extra_boxes=0, tab=navigation.COMBATANTS_TAB):
        """Run the wrapped capture and collect what it warned about.

        Args:
            extra_boxes: Box clicks beyond the one upstream makes today.
            tab: Where the capture taps for the Combatants tab.

        Returns:
            The warning lines the wrapper logged.
        """
        utils_chaos = install(ON_THE_TAB)
        said = []
        original_warning = navigation.logger.warning
        navigation.logger.warning = lambda message, *args, **kwargs: said.append(message)
        try:
            def handle_archive_target_member(task):
                for _ in range(1 + extra_boxes):
                    task.click_box(types.SimpleNamespace(name="memberinfo"))
                utils_chaos._move_and_click(task, *tab)
                return True

            navigation.reading_in_place(handle_archive_target_member)(FakeTask())
        finally:
            navigation.logger.warning = original_warning
        return said

    def test_the_shape_upstream_has_today_says_nothing(self):
        self.assertEqual([], self.warnings())

    def test_a_frame_upstream_declines_says_nothing(self):
        """Off the page upstream returns before tapping, and a live run logged the warning on every such frame."""
        install(ANOTHER_TAB)
        said = []
        original_warning = navigation.logger.warning
        navigation.logger.warning = lambda message, *args, **kwargs: said.append(message)
        try:
            navigation.reading_in_place(lambda task: False)(FakeTask())
        finally:
            navigation.logger.warning = original_warning
        self.assertEqual([], said)

    def test_a_moved_tab_tap_is_reported(self):
        """The skip would quietly stop saving anything, which is the failure nobody would notice."""
        said = self.warnings(tab=(0.250, 0.056))
        self.assertEqual(1, len(said))
        self.assertIn("dropped 0 and 1", said[0])

    def test_a_second_box_click_is_reported(self):
        """This is the sharper one: a tap upstream needed would have been swallowed."""
        said = self.warnings(extra_boxes=1)
        self.assertEqual(1, len(said))
        self.assertIn("dropped 1 and 2", said[0])


class TestSortieTeamTrip(unittest.TestCase):
    """Sortie taps through to the team once a run, and the new run's roster replaces the old party."""

    def tearDown(self):
        for name in ("utils", "utils_chaos"):
            sys.modules.pop(name, None)

    def test_each_run_taps_through_once_and_reads_its_own_party(self):
        install(ON_THE_TAB)
        utils = sys.modules["utils"]
        on_map = [False]
        utils._get_current_hp_percent = lambda task: 100 if on_map[0] else False
        utils._move_and_click = lambda task, x, y: task.clicks.append((x, y))
        task = FakeTask()
        task.sleep = lambda seconds: None
        task.info_set = lambda key, value: None
        task.node_status = {}
        clock = [0.0]

        task.width, task.height = WIDTH, HEIGHT

        with mock.patch.object(navigation.time, "monotonic", lambda: clock[0]):
            self.assertFalse(navigation.handle_open_team(task), "off the map there is nothing to tap")
            on_map[0] = True
            # Live, a restart mid-battle tapped the portraits over the end turn prompt, which ended a turn with a card still playable.
            for shown in ([FakeBox("04/10", 0.5, 0.97)], [FakeBox("取消", 0.34, 0.60)]):
                task.all_texts = shown
                self.assertFalse(navigation.handle_open_team(task), f"{shown[0].name} is not the map")
            task.all_texts = []
            self.assertTrue(navigation.handle_open_team(task))
            # A pending dialog swallowed the tap, and its own handler needs the next frames to clear it.
            self.assertFalse(navigation.handle_open_team(task))
            # Once it has, the team is tapped for again, but not past `TEAM_TRIES`.
            for _ in range(navigation.TEAM_TRIES - 1):
                clock[0] += navigation.TEAM_RETRY_SECONDS
                self.assertTrue(navigation.handle_open_team(task))
            clock[0] += navigation.TEAM_RETRY_SECONDS
            self.assertFalse(navigation.handle_open_team(task))
            self.assertEqual([navigation.TEAM_PORTRAITS] * navigation.TEAM_TRIES, task.clicks)
            task.clicks.clear()

            # Upstream rebuilds `node_status` for the next run, and the last run's party must not outlive it.
            task.node_status = {}
            setattr(task, PARTY, frozenset({"Yuki"}))
            self.assertTrue(navigation.handle_open_team(task))
            self.assertEqual(frozenset(), getattr(task, PARTY))
            self.assertEqual([navigation.TEAM_PORTRAITS], task.clicks)

            rewards.remember_team(task, utils)
            self.assertEqual({"Arabella", "Veronica", "Mika"}, getattr(task, PARTY))
            clock[0] += navigation.TEAM_RETRY_SECONDS
            self.assertFalse(navigation.handle_open_team(task), "a team read stops the retries")

    def test_the_deck_is_read_just_before_the_page_closes(self):
        # Live, the read opened All Piles first and needed a tap back to the Combatants tab before the team could be read.
        utils_chaos = install(ON_THE_TAB)
        capture = piles.reading_the_deck(upstream_capture(utils_chaos), utils_chaos)
        sortie, chaos = type("SortieMode", (FakeTask,), {})(), FakeTask()
        for task in (sortie, chaos):
            task.node_status, task.all_texts = {}, ["Owen"]

        def read_deck(task, utils):
            task.clicks.append("deck")
            task.all_texts = ["All Piles"]

        with standing_in(piles, read_deck=read_deck):
            for task in (sortie, sortie, chaos):
                capture(task)
        self.assertEqual([navigation.COMBATANTS_TAB, "deck", CLOSE_PAGE] + [navigation.COMBATANTS_TAB, CLOSE_PAGE], sortie.clicks)
        self.assertEqual(["Owen"], sortie.all_texts, "the team read after the capture takes its names from the Combatants pass")
        self.assertNotIn("deck", chaos.clicks)


class TestDeckRead(unittest.TestCase):
    """All Piles is read card by card, each card is taken for the version its text matches, and a card is valued by its weakest copy."""

    def tearDown(self):
        cards.use_deck({})

    def test_each_whole_card_is_taken_for_its_version(self):
        task = types.SimpleNamespace(width=WIDTH, height=HEIGHT, all_texts=[FakeBox(text, x, y, width=w, height=h, units="pixels")
                                                                           for text, x, y, w, h in PILES_PAGE])
        # A named card inside a text, or a card cut off at the bottom, would add a fifth. A broken match would land a copy on the base.
        self.assertEqual({
            ("Slash", next(iter(EPIPHANIES["Slash"]))),
            ("Experienced Strike", DESCRIPTIONS["Experienced Strike"]),
            ("Experienced Strike", SHIELD_GAIN),
            ("Hew", DESCRIPTIONS["Hew"]),
        }, {(name, piles.version_of(name, text)) for name, text, _ in piles.cards_on_page(task)})

    def test_a_card_is_valued_by_its_weakest_copy(self):
        base, stronger = cards.figures(DESCRIPTIONS["Experienced Strike"]), cards.figures(SHIELD_GAIN)
        self.assertLess(base.damage, stronger.damage)
        cards.use_deck({"Experienced Strike": {SHIELD_GAIN}})
        self.assertEqual(stronger, cards.features("Experienced Strike"))
        # A second read replaces the first, which a stale cache of the figures would hide.
        cards.use_deck({"Experienced Strike": {SHIELD_GAIN, DESCRIPTIONS["Experienced Strike"]}})
        self.assertEqual(base, cards.features("Experienced Strike"))



class TestEpiphanyChoice(unittest.TestCase):
    """A Sortie Epiphany goes on a card even when the user listed none, and every other choice is left to the pins and the user's lists."""

    def tearDown(self):
        cards.use_deck({})

    def test_the_card_without_an_epiphany_goes_first(self):
        # The three cards a Sortie run offered, where the deck read had found Epiphanies on the first two.
        cards.use_deck({name: {next(iter(EPIPHANIES[name]))} for name in ("Sacred Censer", "Growing Creature")} | {"Annoying": {DESCRIPTIONS["Annoying"]}})
        self.assertEqual("Annoying", epiphany.ranked([{"name": "Sacred Censer"}, {"name": "Growing Creature"}, {"name": "Annoying"}])[0])

    def test_only_a_sortie_epiphany_is_chosen(self):
        utils = types.SimpleNamespace(recognize_cards_in_deck=lambda task, page="": [{"name": "Annoying"}])
        passed = []

        def select_card(task, names, count=1, action=""):
            # Upstream reads the page before matching the names, so the names are taken after the read.
            utils.recognize_cards_in_deck(task)
            passed.append(list(names))

        choose = epiphany.choosing(select_card, utils)
        for mode, action, expected in (
            (epiphany.SORTIE_MODE, epiphany.ACTIONS[0], ["Slash", "Annoying"]),
            ("ChaosMode", epiphany.ACTIONS[0], ["Slash"]),
            (epiphany.SORTIE_MODE, "", ["Slash"]),
        ):
            with self.subTest(mode=mode, action=action):
                passed.clear()
                choose(type(mode, (), {})(), ["Slash"], action=action)
                self.assertEqual([expected], passed)


if __name__ == "__main__":
    unittest.main()
