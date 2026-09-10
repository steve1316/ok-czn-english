"""Check that the Season 3 Persona card screen can see its own cards on the Global client.

`handle_mask_card` picks one of three Persona cards, and it finds them by testing each recognised card's name
for the Chinese literal 人格面具. On the Global client the reader returns English names, so that list is always
empty, `len(mask_cards) < 3` is always true, and the handler silently takes its "a Persona has already been
chosen, skip" branch on every Persona screen there has ever been.

A catalog entry cannot fix it: the literal is tested against a card *name*, and rewriting names would break
every priority list the user fills in. The names are marked for upstream's filter instead, for the length of
one call, which leaves the name the user's list matches against untouched.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en.persona import ENGLISH, MASK, install, marking_personas  # noqa: E402


class FakeTask:
    """A task that records nothing but its own identity."""

    width, height = 1920, 1080


def card(name):
    """Build the card dict the recognizer produces.

    Args:
        name: The card's name.

    Returns:
        A card dict.
    """
    return {"name": name, "x": 0.5, "y": 0.3, "description": "", "type": "技能"}


class TestMarkingPersonas(unittest.TestCase):
    """What upstream's filter is shown."""

    @staticmethod
    def utils_stub(cards):
        """Build a stand-in carrying the recognizer the handler reads through.

        Args:
            cards: What that recognizer returns.

        Returns:
            A namespace with `recognize_cards`.
        """
        return types.SimpleNamespace(recognize_cards=lambda *a, **k: cards)

    def seen(self, names):
        """Run the wrapped handler and report the names upstream was handed.

        Args:
            names: The card names the reader produced.

        Returns:
            The names as upstream's filter saw them.
        """
        utils = self.utils_stub([card(name) for name in names])
        got = []

        def handler(task):
            got.extend(c["name"] for c in utils.recognize_cards(task))
            return True

        marking_personas(handler, utils)(FakeTask())
        return got

    def test_an_english_persona_carries_the_literal_upstream_looks_for(self):
        self.assertTrue(all(MASK in name for name in self.seen(["Persona of Loss"])))

    def test_every_persona_on_the_screen_is_marked(self):
        names = ["Persona of Loss", "Distortion: Persona of Loss", "Persona"]
        self.assertEqual(3, sum(MASK in name for name in self.seen(names)))

    def test_an_ordinary_card_is_left_alone(self):
        self.assertEqual(["Aimed Fire"], self.seen(["Aimed Fire"]))

    def test_a_chinese_client_is_untouched(self):
        # The literal is already there, so nothing is added and the name stays exactly as it was.
        self.assertEqual(["人格面具·丧失"], self.seen(["人格面具·丧失"]))

    def test_the_name_the_user_matches_against_survives(self):
        # Priority lists are matched against the name, so the English half has to remain readable.
        self.assertTrue(all(ENGLISH in name for name in self.seen(["Persona of Loss"])))

    def test_restores_the_recognizer_afterwards(self):
        utils = self.utils_stub([])
        before = utils.recognize_cards
        marking_personas(lambda task: True, utils)(FakeTask())
        self.assertIs(utils.recognize_cards, before)

    def test_restores_the_recognizer_when_the_handler_raises(self):
        utils = self.utils_stub([])
        before = utils.recognize_cards

        def raising(task):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            marking_personas(raising, utils)(FakeTask())
        self.assertIs(utils.recognize_cards, before)


class TestInstall(unittest.TestCase):
    """Patching the module that actually resolves the call."""

    def setUp(self):
        self.utils = types.ModuleType("utils_for_persona_test")
        self.utils.recognize_cards = lambda *a, **k: []
        self.chaos = types.ModuleType("utils_chaos_for_persona_test")
        # Chaos does `from utils import recognize_cards`, so it holds its own reference to the same function.
        self.chaos.recognize_cards = self.utils.recognize_cards
        self.chaos.handle_mask_card = self.handler()
        self.chaos.PAGE_HANDLERS = [self.chaos.handle_mask_card]
        sys.modules["utils_chaos"] = self.chaos

    def tearDown(self):
        sys.modules.pop("utils_chaos", None)

    @staticmethod
    def handler():
        """Build a stand-in for the Persona handler.

        Returns:
            A function carrying upstream's name.
        """
        def handle_mask_card(task):
            return True

        return handle_mask_card

    def test_the_wrapper_lands_on_the_module_that_calls_the_recognizer(self):
        # Patching `utils` would change nothing here: Chaos imported the function, so its own name is what
        # line 623 resolves through.
        before = self.chaos.handle_mask_card
        install(self.utils)
        self.assertIsNot(self.chaos.handle_mask_card, before)
        self.assertEqual("handle_mask_card", self.chaos.handle_mask_card.__name__)

    def test_the_names_are_marked_through_that_same_module(self):
        seen = []

        def handle_mask_card(task):
            seen.extend(c["name"] for c in self.chaos.recognize_cards(task))
            return True

        self.chaos.handle_mask_card = handle_mask_card
        self.chaos.recognize_cards = lambda *a, **k: [card("Persona of Loss")]
        install(self.utils)
        self.chaos.handle_mask_card(FakeTask())
        self.assertTrue(all(MASK in name for name in seen))

    def test_running_twice_does_not_nest(self):
        install(self.utils)
        once = self.chaos.handle_mask_card
        install(self.utils)
        self.assertIs(self.chaos.handle_mask_card, once)

    def test_tolerates_a_missing_module(self):
        install(None)


if __name__ == "__main__":
    unittest.main()
