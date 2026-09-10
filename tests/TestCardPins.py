"""Check that a card pinned by the user's build preset is the one taken.

The client draws a small orange pin in the top-right corner of any card a build preset names. Nothing in
`ok_tasks/` knows it exists, so the pick has always come down to the priority lists alone.

Every number here was measured off the captured screens rather than guessed. The pin sits a fixed distance
from the card's own type icon, which is the anchor the recognizer already works from, and the two card layouts
in use put it at two different offsets. Sampled at those offsets the pin filled about two thirds of the probe
and an unpinned card none of it, on a glittering screen as well as a plain one, so the threshold sits far from
both.
"""

import sys
import types
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.pins import (  # noqa: E402
    CHOOSERS, DECK_OFFSET, PICK_OFFSET, PROBE, RECOGNIZERS, install, is_pinned, marked,
    narrowing, only_pinned, probe_box, tagging,
)

WIDTH, HEIGHT = 1920, 1080
# The orange the pin is drawn in, and a colour from an unpinned card's corner, both sampled from the captures.
PIN_BGR = (41, 120, 239)
PLAIN_BGR = (115, 115, 113)


class FakeBox:
    """A template match, positioned the way `find_feature` reports one."""

    def __init__(self, center_x, center_y):
        self.width, self.height = 21, 21
        self.x = center_x - self.width / 2
        self.y = center_y - self.height / 2
        self.confidence = 0.93


class FakeTask:
    """A task holding one frame of a card screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self):
        self.frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        self.logged = []

    def paint(self, center_x, center_y, colour):
        """Fill a pin-sized patch of the frame.

        Args:
            center_x: Patch centre, in pixels.
            center_y: Patch centre, in pixels.
            colour: The BGR colour to fill it with.
        """
        half = 15
        self.frame[center_y - half:center_y + half, center_x - half:center_x + half] = colour

    def log_info(self, message):
        self.logged.append(message)


def card(center_x, center_y, name="Joker"):
    """Build the card dict the recognizer produces, anchored on its type icon.

    Args:
        center_x: The type icon's centre, in pixels.
        center_y: The type icon's centre, in pixels.
        name: The card's name.

    Returns:
        A dict carrying the feature box the pin is measured from.
    """
    return {"name": name, "x": center_x / WIDTH, "y": center_y / HEIGHT,
            "feature_box": FakeBox(center_x, center_y)}


def screen_with(pinned, offset):
    """Build a frame where exactly the named cards carry a pin.

    Args:
        pinned: One bool per card, left to right.
        offset: The layout's pin offset.

    Returns:
        A `(task, cards)` pair.
    """
    task = FakeTask()
    cards = []
    for index, is_pin in enumerate(pinned):
        icon_x, icon_y = 400 + index * 320, 424
        cards.append(card(icon_x, icon_y, name=f"card{index}"))
        pin_x = round(icon_x + offset[0] * WIDTH)
        pin_y = round(icon_y + offset[1] * HEIGHT)
        task.paint(pin_x, pin_y, PIN_BGR if is_pin else PLAIN_BGR)
    return task, cards


class TestProbeBox(unittest.TestCase):
    """Where the pin is looked for."""

    def test_sits_at_the_measured_offset_from_the_icon(self):
        # Within a pixel: an odd-sized patch cannot centre exactly on every point, and the pin it sits in
        # is 29 across, so a pixel of slack costs nothing.
        x, y = probe_box(FakeTask(), card(400, 424)["feature_box"], DECK_OFFSET)
        self.assertAlmostEqual(400 + DECK_OFFSET[0] * WIDTH, x + PROBE / 2, delta=1)
        self.assertAlmostEqual(424 + DECK_OFFSET[1] * HEIGHT, y + PROBE / 2, delta=1)

    def test_is_clamped_to_the_frame(self):
        x, y = probe_box(FakeTask(), card(WIDTH - 4, 20)["feature_box"], PICK_OFFSET)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + PROBE, WIDTH)
        self.assertLessEqual(y + PROBE, HEIGHT)


class TestIsPinned(unittest.TestCase):
    """Reading the pin off the frame."""

    def test_reads_a_pin(self):
        task, cards = screen_with([True], DECK_OFFSET)
        self.assertTrue(is_pinned(task, cards[0], DECK_OFFSET))

    def test_reads_a_plain_corner(self):
        task, cards = screen_with([False], DECK_OFFSET)
        self.assertFalse(is_pinned(task, cards[0], DECK_OFFSET))

    def test_reads_the_larger_layout(self):
        task, cards = screen_with([True], PICK_OFFSET)
        self.assertTrue(is_pinned(task, cards[0], PICK_OFFSET))

    def test_a_speck_of_orange_is_not_a_pin(self):
        # Glitter on the Epiphany screen puts a few amber pixels almost anywhere.
        task, cards = screen_with([False], DECK_OFFSET)
        x, y = probe_box(task, cards[0]["feature_box"], DECK_OFFSET)
        task.frame[y:y + 3, x:x + 3] = PIN_BGR
        self.assertFalse(is_pinned(task, cards[0], DECK_OFFSET))

    def test_declines_without_a_frame(self):
        task, cards = screen_with([True], DECK_OFFSET)
        task.frame = None
        self.assertFalse(is_pinned(task, cards[0], DECK_OFFSET))


class TestOnlyPinned(unittest.TestCase):
    """Narrowing the candidates to the pinned ones."""

    def narrowed(self, pinned):
        """Mark a screen and narrow it.

        Args:
            pinned: One bool per card, left to right.

        Returns:
            The names that survived, and the marks that were recorded.
        """
        task, cards = screen_with(pinned, DECK_OFFSET)
        marked(task, cards, DECK_OFFSET)
        return [c["name"] for c in only_pinned(cards)], [c["pinned"] for c in cards]

    def test_keeps_only_the_pinned_cards(self):
        self.assertEqual(["card1", "card2"], self.narrowed([False, True, True])[0])

    def test_leaves_the_list_alone_when_nothing_is_pinned(self):
        self.assertEqual(["card0", "card1"], self.narrowed([False, False])[0])

    def test_leaves_the_list_alone_when_everything_is_pinned(self):
        self.assertEqual(["card0", "card1"], self.narrowed([True, True])[0])

    def test_marks_each_card(self):
        self.assertEqual([False, True], self.narrowed([False, True])[1])

    def test_handles_an_empty_screen(self):
        self.assertEqual([], only_pinned([]))

    def test_treats_an_unmarked_card_as_unpinned(self):
        # Cards reach this from paths the marker never wrapped, and those must not all vanish.
        cards = [{"name": "a"}, {"name": "b"}]
        self.assertEqual(cards, only_pinned(cards))


class TestTagging(unittest.TestCase):
    """Marking every card a recognizer returns."""

    def test_marks_without_withholding(self):
        # Several callers count what they were handed, so the recognizer itself must never narrow.
        task, cards = screen_with([False, True], DECK_OFFSET)
        wrapped = tagging(lambda task_, **kwargs: cards, DECK_OFFSET)
        got = wrapped(task)
        self.assertEqual(["card0", "card1"], [c["name"] for c in got])
        self.assertEqual([False, True], [c["pinned"] for c in got])

    def test_passes_its_arguments_through(self):
        seen = {}

        def recognise(task_, region=None, page=""):
            seen["region"] = region
            seen["page"] = page
            return []

        tagging(recognise, DECK_OFFSET)(FakeTask(), region=(0.1, 0.2, 0.3, 0.4), page="x")
        self.assertEqual({"region": (0.1, 0.2, 0.3, 0.4), "page": "x"}, seen)

    def test_survives_a_card_with_no_feature_box(self):
        # `handle_stuck_log` builds cards from a different path, so the anchor is not guaranteed.
        wrapped = tagging(lambda task_, **kwargs: [{"name": "odd", "x": 0.5, "y": 0.5}], DECK_OFFSET)
        self.assertEqual([False], [c["pinned"] for c in wrapped(FakeTask())])


class TestNarrowing(unittest.TestCase):
    """Withholding the unpinned cards for the length of one choice."""

    @staticmethod
    def utils_stub(cards):
        """Build a stand-in carrying the recognizer a chooser reads through.

        Args:
            cards: What that recognizer returns.

        Returns:
            A namespace with `recognize_cards_in_deck`.
        """
        return types.SimpleNamespace(recognize_cards_in_deck=lambda *a, **k: cards)

    def test_the_chooser_sees_only_pinned_cards(self):
        task, cards = screen_with([False, True], DECK_OFFSET)
        marked(task, cards, DECK_OFFSET)
        utils = self.utils_stub(cards)
        seen = []

        def chooser(task_):
            seen.append([c["name"] for c in utils.recognize_cards_in_deck(task_)])
            return True

        narrowing(chooser, utils, "recognize_cards_in_deck")(task)
        self.assertEqual([["card1"]], seen)

    def test_passes_arguments_and_result_through(self):
        utils = self.utils_stub([])
        wrapped = narrowing(lambda task_, names, count=1, action="": (names, count, action),
                            utils, "recognize_cards_in_deck")
        self.assertEqual((["a"], 2, "移除"), wrapped(FakeTask(), ["a"], count=2, action="移除"))

    def test_only_the_choosing_sites_narrow(self):
        # The counting callers - handle_mask_card above all - must not be on this list.
        self.assertEqual({"select_card", "handle_card_reward", "handle_view_original"}, set(CHOOSERS))


def named(name):
    """Build a stand-in handler carrying a given name.

    Args:
        name: The `__name__` the handler should report.

    Returns:
        A function that declines every frame.
    """
    def handler(task):
        return False

    handler.__name__ = name
    return handler


class TestInstall(unittest.TestCase):
    """Putting the wrappers where the run will actually reach them."""

    def setUp(self):
        self.recognizers = {"recognize_cards": lambda *a, **k: [],
                            "recognize_cards_in_deck": lambda *a, **k: []}
        self.utils = types.SimpleNamespace(
            recognize_cards=self.recognizers["recognize_cards"],
            recognize_cards_in_deck=self.recognizers["recognize_cards_in_deck"],
            select_card=named("select_card"),
            handle_card_reward=named("handle_card_reward"),
            handle_view_original=named("handle_view_original"),
        )
        self.module = types.ModuleType("fake_mode_for_pins_test")
        self.module.PAGE_HANDLERS = [named("handle_card_reward"), named("handle_view_original")]
        sys.modules[self.module.__name__] = self.module

    def tearDown(self):
        sys.modules.pop(self.module.__name__, None)

    def names(self):
        """Report the handler list as names.

        Returns:
            A list of `__name__`.
        """
        return [h.__name__ for h in self.module.PAGE_HANDLERS]

    def test_marks_both_recognizers(self):
        install(self.utils)
        for name in RECOGNIZERS:
            with self.subTest(name=name):
                self.assertEqual([], getattr(self.utils, name)(FakeTask()))
                self.assertIsNot(getattr(self.utils, name), self.recognizers[name])

if __name__ == "__main__":
    unittest.main()
