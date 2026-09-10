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

from src.en import deck, desire, equipment, pins, shop  # noqa: E402
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


class TestDesireRegistration(unittest.TestCase):
    """Where the two Desire screens are claimed from."""

    def setUp(self):
        self.utils = fake_utils()
        self.module = types.ModuleType("fake_mode_for_desire_test")
        self.module.PAGE_HANDLERS = [named(name) for name in
                                     ("handle_equipment", "handle_confirm", "handle_shop",
                                      "handle_card_reward", "handle_view_original")]
        sys.modules[self.module.__name__] = self.module

    def tearDown(self):
        sys.modules.pop(self.module.__name__, None)

    def names(self):
        """Report the handler list as names.

        Returns:
            A list of `__name__`.
        """
        return [handler.__name__ for handler in self.module.PAGE_HANDLERS]

    def test_the_reward_screen_outranks_the_confirm_button(self):
        # The screen's Confirm is greyed until a card is chosen, so the confirm handler spinning on it is
        # exactly what stalled the run for ten seconds.
        desire.install(self.utils)
        listed = self.names()
        self.assertLess(listed.index("handle_desire_reward"), listed.index("handle_confirm"))

    def test_the_inherit_screen_outranks_the_ordinary_card_reward(self):
        # Both screens are titled "Card Reward"; whichever handler runs first claims it, and upstream's
        # presses Skip.
        desire.install(self.utils)
        listed = self.names()
        self.assertLess(listed.index("handle_desire_inherit"), listed.index("handle_card_reward"))

    def test_installing_again_does_not_duplicate(self):
        for _ in range(MODES):
            desire.install(self.utils)
        listed = self.names()
        for name in ("handle_desire_reward", "handle_desire_inherit"):
            with self.subTest(name=name):
                self.assertEqual(1, listed.count(name))

    def test_a_mode_loaded_later_gets_them_too(self):
        desire.install(self.utils)
        later = types.ModuleType("fake_late_mode_for_desire_test")
        later.PAGE_HANDLERS = [named("handle_confirm"), named("handle_card_reward")]
        sys.modules[later.__name__] = later
        try:
            desire.install(self.utils)
            listed = [handler.__name__ for handler in later.PAGE_HANDLERS]
            self.assertIn("handle_desire_reward", listed)
            self.assertIn("handle_desire_inherit", listed)
        finally:
            sys.modules.pop(later.__name__, None)

    def test_tolerates_a_missing_module(self):
        desire.install(None)


if __name__ == "__main__":
    unittest.main()
