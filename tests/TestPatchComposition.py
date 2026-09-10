"""Check that the fork's patches stack on each other instead of fighting.

Several modules wrap the same upstream function - `select_card` is wrapped by both the pin filter and the
row preference - and every install runs once per task load, once per mode. Before `handlers.wrap` each module
carried its own marker attribute, so neither could see the other's, and the stack grew by one layer per module
per load. Nothing failed loudly; the wrappers just piled up for the life of the process.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import deck, equipment, pins, shop  # noqa: E402
from src.en.handlers import WRAPS  # noqa: E402

MODES = 3


def named(name):
    """Build a stand-in handler carrying a given name.

    Args:
        name: The `__name__` the handler should report.

    Returns:
        A function that declines every frame.
    """
    def handler(*args, **kwargs):
        return False

    handler.__name__ = name
    return handler


def fake_utils():
    """Build a stand-in for `utils` carrying every function the four modules patch.

    Returns:
        A namespace.
    """
    return types.SimpleNamespace(
        handle_shop=named("handle_shop"),
        handle_equipment=named("handle_equipment"),
        handle_card_reward=named("handle_card_reward"),
        handle_view_original=named("handle_view_original"),
        select_card=named("select_card"),
        recognize_cards=named("recognize_cards"),
        recognize_cards_in_deck=named("recognize_cards_in_deck"),
        _get_current_credit=lambda task: 0,
    )


class TestPatchComposition(unittest.TestCase):
    """Installing every module, as many times as the run would."""

    def setUp(self):
        self.utils = fake_utils()
        self.module = types.ModuleType("fake_mode_for_composition_test")
        self.module.PAGE_HANDLERS = [named(name) for name in
                                     ("handle_equipment", "handle_shop", "handle_card_reward",
                                      "handle_view_original")]
        sys.modules[self.module.__name__] = self.module

    def tearDown(self):
        sys.modules.pop(self.module.__name__, None)

    def install_all(self):
        """Run every module's install, the way one task load does."""
        for module in (pins, deck, equipment, shop):
            module.install(self.utils)

    def test_select_card_carries_both_changes(self):
        self.install_all()
        self.assertEqual({pins.NARROW_TAG, deck.TAG}, set(getattr(self.utils.select_card, WRAPS)))

    def test_select_card_does_not_stack_over_repeated_loads(self):
        for _ in range(MODES):
            self.install_all()
        self.assertEqual(2, len(getattr(self.utils.select_card, WRAPS)))

    def test_equipment_carries_both_changes_once(self):
        for _ in range(MODES):
            self.install_all()
        self.assertEqual([equipment.RECOMMENDED_TAG, equipment.MYTHIC_TAG],
                         list(getattr(self.utils.handle_equipment, WRAPS)))

    def test_the_card_reward_screen_carries_the_pin_filter_once(self):
        for _ in range(MODES):
            self.install_all()
        self.assertEqual([pins.NARROW_TAG], list(getattr(self.utils.handle_card_reward, WRAPS)))

    def test_every_patched_handler_reaches_the_mode_list(self):
        self.install_all()
        for handler in self.module.PAGE_HANDLERS:
            with self.subTest(handler=handler.__name__):
                self.assertIs(handler, getattr(self.utils, handler.__name__))

    def test_the_order_modules_install_in_does_not_matter(self):
        one = fake_utils()
        for module in (pins, deck, equipment, shop):
            module.install(one)
        other = fake_utils()
        for module in (shop, equipment, deck, pins):
            module.install(other)
        self.assertEqual(set(getattr(one.select_card, WRAPS)), set(getattr(other.select_card, WRAPS)))


if __name__ == "__main__":
    unittest.main()
