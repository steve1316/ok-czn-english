"""Check the edits made to a mode's ordered list of page handlers.

`src/en/handlers.py` is what every fork-local behaviour change goes through, and its failure modes are silent
rather than loud. Position in the list *is* the priority scheme, so an edit that lands at the wrong index
changes which handler claims a screen. The installs also run once per task load, so anything not idempotent
accumulates duplicates over a session rather than failing outright.
"""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import handlers  # noqa: E402


def named(name):
    """Build a stand-in handler that reports the given name.

    Args:
        name: The `__name__` the handler should carry.

    Returns:
        A function.
    """
    def handler(task):
        return False
    handler.__name__ = name
    return handler


class TestHandlerSeam(unittest.TestCase):

    def setUp(self):
        # A module shaped like utils_chaos, registered so `each_list` discovers it the way it does at runtime.
        self.module = types.ModuleType("fake_mode_for_test")
        self.module.PAGE_HANDLERS = [named(n) for n in
                                     ("handle_close_page", "handle_negotiation", "handle_event_task")]
        sys.modules[self.module.__name__] = self.module

    def tearDown(self):
        sys.modules.pop(self.module.__name__, None)

    def names(self):
        """Read the current handler names in order.

        Returns:
            A list of names.
        """
        return [h.__name__ for h in self.module.PAGE_HANDLERS]

    def test_a_handler_is_replaced_in_place(self):
        """Position is priority, so a replacement must take the original's index, not be appended."""
        handlers.replace("handle_event_task", named("patched_handle_event_task"))
        self.assertEqual(["handle_close_page", "handle_negotiation", "patched_handle_event_task"], self.names())

    def test_replacing_leaves_the_other_handlers_alone(self):
        handlers.replace("handle_negotiation", named("patched"))
        self.assertEqual(["handle_close_page", "patched", "handle_event_task"], self.names())

    def test_a_handler_is_inserted_directly_before_its_anchor(self):
        """Before the anchor rather than at the front, so everything above keeps its precedence."""
        handlers.insert_before("handle_negotiation", named("handle_dice_reroll"))
        self.assertEqual(["handle_close_page", "handle_dice_reroll", "handle_negotiation",
                          "handle_event_task"], self.names())

    def test_inserting_twice_does_not_duplicate(self):
        """The install runs on every task load, and each run builds a fresh function object."""
        for _ in range(3):
            handlers.insert_before("handle_negotiation", named("handle_dice_reroll"))
        self.assertEqual(1, self.names().count("handle_dice_reroll"))

    def test_replacing_twice_does_not_stack(self):
        for _ in range(3):
            handlers.replace("handle_event_task", named("patched_handle_event_task"))
        self.assertEqual(1, self.names().count("patched_handle_event_task"))
        self.assertEqual(3, len(self.module.PAGE_HANDLERS))

    def test_an_unknown_handler_changes_nothing(self):
        """A rename upstream must leave the mode running upstream's behaviour, not crash the load."""
        before = self.names()
        self.assertEqual(0, handlers.replace("handle_that_was_renamed", named("ours")))
        self.assertEqual(0, handlers.insert_before("handle_that_was_renamed", named("ours")))
        self.assertEqual(before, self.names())

    def test_a_module_without_a_handler_list_is_skipped(self):
        """Most of sys.modules has no PAGE_HANDLERS, and one mode's list holds neither handler we touch."""
        other = types.ModuleType("fake_mode_without_handlers")
        other.PAGE_HANDLERS = "not a list"
        sys.modules[other.__name__] = other
        try:
            handlers.replace("handle_event_task", named("patched"))
            self.assertEqual("not a list", other.PAGE_HANDLERS)
        finally:
            sys.modules.pop(other.__name__, None)


if __name__ == "__main__":
    unittest.main()
