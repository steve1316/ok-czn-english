"""Check that the Chaos start page is re-observed for a blacklisted modifier, and entered once the currency runs short.

The panel boxes are the OCR of the Celestial Bulwark start page on the Global client, 2026-10-29.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.reobserve import MODIFIER_BLACKLIST, REOBSERVE, SAVE_LIMIT_KEY, modifiers_in, reobserving  # noqa: E402
from tests.fakes import HEIGHT, WIDTH, FakeBox  # noqa: E402

TITLE = FakeBox("Chaos", 0.117, 0.046, units="fraction")
REOBSERVE_BUTTON = FakeBox("Re-observe", 0.773, 0.794, width=180, units="fraction")
COST = FakeBox("10", 0.955, 0.794, units="fraction")
# The top bar: the Loot Certification count, the event currency, and a stray icon read as a digit beside it.
TOP_BAR = [FakeBox("0/4+", 0.703, 0.045, units="fraction"), FakeBox("434", 0.846, 0.048, units="fraction"), FakeBox("0", 0.899, 0.052, units="fraction")]
# Difficulty VI: four modifiers, the last one's description running off the bottom of the panel.
ANXIETY_PLAGUE = [
    FakeBox("- Save Data Storage Limit 140pt", 0.805, 0.400, width=500, units="fraction"),
    FakeBox("[Anxiety 1] Cannot rest in Safe Zone", 0.827, 0.543, width=560, units="fraction"),
    FakeBox("[Elite 3]: Add 6 Elite Areas", 0.793, 0.584, width=420, units="fraction"),
    FakeBox("[Plague 1]Decrease Max HP by 50%", 0.827, 0.626, width=560, units="fraction"),
    FakeBox("Tyrant 2: Increase Attack and Health of", 0.834, 0.667, width=580, units="fraction"),
    FakeBox("monsters in Elite and Boss Areas by", 0.824, 0.700, width=560, units="fraction"),
]
# Difficulty VII: Tyrant alone, whose wrapped second line names Elite Areas.
TYRANT_ONLY = [
    FakeBox("- Save Data Storage Limit 120pt", 0.806, 0.402, width=500, units="fraction"),
    FakeBox("Tyrant 3: Increase Attack and Health of", 0.836, 0.543, width=580, units="fraction"),
    FakeBox("monsters in Elite and Boss Areas by", 0.825, 0.576, width=560, units="fraction"),
    FakeBox("30%", 0.726, 0.606, units="fraction"),
]
# Difficulty X, its OCR gluing the Loss tag to its percentage.
NEGLECT_LOSS_GANGRENE = [
    FakeBox("- Save Data Storage Limit 140pt", 0.805, 0.400, width=500, units="fraction"),
    FakeBox("[Neglect 1] Discard 1 card randomly at", 0.834, 0.543, width=580, units="fraction"),
    FakeBox("the start of each turn", 0.778, 0.575, width=320, units="fraction"),
    FakeBox("[Loss 1]-40% Credits gained from", 0.821, 0.617, width=500, units="fraction"),
    FakeBox("battle", 0.730, 0.649, units="fraction"),
    FakeBox("[Gangrene 1] At the start of each turn", 0.830, 0.690, width=580, units="fraction"),
]


class FakeTask:
    """The Chaos start page, recording the boxes clicked on it."""

    def __init__(self, boxes, **config):
        self.all_texts = boxes
        self.width, self.height = WIDTH, HEIGHT
        self.config = {SAVE_LIMIT_KEY: 0, REOBSERVE: True, MODIFIER_BLACKLIST: ["Anxiety", "Plague"], **config}
        self.clicked = []

    def click_box(self, box, *args, **kwargs):
        self.clicked.append(box)

    def log_info(self, message):
        pass

    def sleep(self, seconds):
        pass


# Upstream's config reader, as far as this handler leans on it.
UTILS_CHAOS = types.SimpleNamespace(_get_config_value=lambda task, key, default: task.config.get(key, default))


def start_page(panel, currency=TOP_BAR, **config):
    return FakeTask([TITLE, *currency, *panel, REOBSERVE_BUTTON, COST], **config)


class TestReobserve(unittest.TestCase):

    def test_only_a_tag_opening_a_line_counts_as_a_modifier(self):
        """Tyrant's wrapped line names Elite Areas, which would blacklist every Tyrant roll for someone avoiding Elite."""
        for panel, expected in ((ANXIETY_PLAGUE, ["Anxiety", "Elite", "Plague", "Tyrant"]), (TYRANT_ONLY, ["Tyrant"]),
                                (NEGLECT_LOSS_GANGRENE, ["Neglect", "Loss", "Gangrene"])):
            with self.subTest(expected=expected):
                self.assertEqual(expected, modifiers_in([box.name for box in panel]))

    def test_each_start_page(self):
        upstream = []
        handler = reobserving(lambda task: upstream.append(task) or "upstream", UTILS_CHAOS)
        cases = (
            ("blacklisted and affordable", start_page(ANXIETY_PLAGUE), True, [REOBSERVE_BUTTON]),
            ("blacklisted but broke", start_page(ANXIETY_PLAGUE, currency=[FakeBox("9", 0.846, 0.048, units="fraction")]), False, []),
            ("currency unread", start_page(ANXIETY_PLAGUE, currency=[]), False, []),
            ("switched off", start_page(ANXIETY_PLAGUE, **{REOBSERVE: False}), False, []),
            ("nothing blacklisted", start_page(NEGLECT_LOSS_GANGRENE), False, []),
            # The save limit still re-observes with the blacklist off, as upstream's own rule.
            ("save limit too low", start_page(TYRANT_ONLY, **{SAVE_LIMIT_KEY: 140, REOBSERVE: False}), True, [REOBSERVE_BUTTON]),
        )
        for label, task, claimed, clicked in cases:
            with self.subTest(label):
                self.assertEqual(claimed, handler(task))
                self.assertEqual(clicked, task.clicked)
        self.assertEqual([], upstream)

    def test_a_page_without_the_english_title_and_button_is_left_to_upstream(self):
        """The Chinese clients still re-observe through upstream's own literals, and a Re-observe on another screen is not pressed."""
        for label, boxes in (("Chinese client", [TITLE, FakeBox("再次观测", 0.773, 0.794, units="fraction")]), ("no title", [REOBSERVE_BUTTON])):
            with self.subTest(label):
                task = FakeTask([*TOP_BAR, *ANXIETY_PLAGUE, *boxes, COST])
                self.assertEqual("upstream", reobserving(lambda task: "upstream", UTILS_CHAOS)(task))
                self.assertEqual([], task.clicked)


if __name__ == "__main__":
    unittest.main()
