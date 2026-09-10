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

    def test_an_appended_handler_runs_after_everything_else(self):
        """Last is the point: it only sees a frame no handler that knows a screen by name has claimed."""
        handlers.append(named("handle_dialogue"), "handle_event_task")
        self.assertEqual(["handle_close_page", "handle_negotiation", "handle_event_task",
                          "handle_dialogue"], self.names())

    def test_appending_twice_does_not_duplicate(self):
        for _ in range(3):
            handlers.append(named("handle_dialogue"), "handle_event_task")
        self.assertEqual(1, self.names().count("handle_dialogue"))

    def test_a_mode_without_the_anchor_is_left_alone(self):
        """Appending has no brake of its own, so the anchor is what keeps a handler tuned on one mode's
        screens out of the modes it was never measured against."""
        before = self.names()
        self.assertEqual(0, handlers.append(named("handle_dialogue"), "handle_that_mode_does_not_have"))
        self.assertEqual(before, self.names())

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


class TestStandingIn(unittest.TestCase):
    """Swapping attributes for the length of one call."""

    def setUp(self):
        self.module = types.SimpleNamespace(first="a", second="b")

    def test_swaps_for_the_length_of_the_block(self):
        with handlers.standing_in(self.module, first="x"):
            self.assertEqual("x", self.module.first)
        self.assertEqual("a", self.module.first)

    def test_swaps_several_at_once(self):
        with handlers.standing_in(self.module, first="x", second="y"):
            self.assertEqual(("x", "y"), (self.module.first, self.module.second))
        self.assertEqual(("a", "b"), (self.module.first, self.module.second))

    def test_restores_when_the_block_raises(self):
        # A handler that throws must not leave upstream's module permanently rewired.
        with self.assertRaises(ValueError):
            with handlers.standing_in(self.module, first="x", second="y"):
                raise ValueError("boom")
        self.assertEqual(("a", "b"), (self.module.first, self.module.second))

    def test_leaves_untouched_attributes_alone(self):
        with handlers.standing_in(self.module, first="x"):
            self.assertEqual("b", self.module.second)

    def test_nests(self):
        with handlers.standing_in(self.module, first="x"):
            with handlers.standing_in(self.module, first="y"):
                self.assertEqual("y", self.module.first)
            self.assertEqual("x", self.module.first)
        self.assertEqual("a", self.module.first)

    def test_swapping_nothing_is_allowed(self):
        with handlers.standing_in(self.module):
            self.assertEqual("a", self.module.first)

    def test_a_method_goes_back_to_the_class_rather_than_onto_the_instance(self):
        """Setting a bound copy back by name would shadow the class for the rest of the object's life, and
        hold a reference cycle with it. Both matter here: the objects stood in for are the modes, which live
        as long as the app does."""
        class Task:
            def click_box(self, box):
                return "upstream"

        task = Task()
        with handlers.standing_in(task, click_box=lambda box: "stood in"):
            self.assertEqual("stood in", task.click_box(None))
        self.assertEqual("upstream", task.click_box(None))
        self.assertNotIn("click_box", vars(task))

    def test_an_attribute_the_object_owns_is_put_back_on_it(self):
        """The other half of the same rule: `all_texts` is the mode's own, so it has to be restored, not
        removed."""
        class Task:
            def __init__(self):
                self.all_texts = ["a", "b"]

        task = Task()
        with handlers.standing_in(task, all_texts=["c"]):
            self.assertEqual(["c"], task.all_texts)
        self.assertEqual(["a", "b"], task.all_texts)
        self.assertIn("all_texts", vars(task))

    def test_a_method_is_put_back_when_the_block_raises(self):
        class Task:
            def click_box(self, box):
                return "upstream"

        task = Task()
        with self.assertRaises(ValueError):
            with handlers.standing_in(task, click_box=lambda box: "stood in"):
                raise ValueError("boom")
        self.assertNotIn("click_box", vars(task))


class TestWrap(unittest.TestCase):
    """Composing fork-local wrappers over one upstream function."""

    def setUp(self):
        self.utils = types.SimpleNamespace(handle_thing=named("handle_thing"))
        self.module = types.ModuleType("fake_mode_for_wrap_test")
        self.module.PAGE_HANDLERS = [named("handle_thing"), named("handle_other")]
        sys.modules[self.module.__name__] = self.module

    def tearDown(self):
        sys.modules.pop(self.module.__name__, None)

    @staticmethod
    def marking(mark):
        """Build a factory whose wrapper records that it ran.

        Args:
            mark: What the wrapper appends to the list it is given.

        Returns:
            A factory taking the function to wrap.
        """
        def factory(inner):
            def wrapped(seen):
                seen.append(mark)
                return inner(seen)

            return wrapped

        return factory

    def test_installs_on_the_module_and_in_the_list(self):
        handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
        self.assertIs(self.module.PAGE_HANDLERS[0], self.utils.handle_thing)
        self.assertEqual("handle_thing", self.utils.handle_thing.__name__)

    def test_a_second_module_composes_rather_than_replacing(self):
        handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
        handlers.wrap(self.utils, "handle_thing", self.marking("b"), "b")
        seen = []
        self.utils.handle_thing(seen)
        self.assertEqual(["b", "a"], seen)

    def test_running_every_install_again_does_not_stack(self):
        # The installs run once per task load, and two modules wrapping the same function used to grow the
        # stack by one layer each every time, because neither could see the other's marker.
        for _ in range(3):
            handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
            handlers.wrap(self.utils, "handle_thing", self.marking("b"), "b")
        seen = []
        self.utils.handle_thing(seen)
        self.assertEqual(["b", "a"], seen)

    def test_a_mode_loaded_later_still_gets_the_wrapper(self):
        handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
        later = types.ModuleType("fake_late_mode_for_wrap_test")
        later.PAGE_HANDLERS = [named("handle_thing")]
        sys.modules[later.__name__] = later
        try:
            handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
            self.assertIs(later.PAGE_HANDLERS[0], self.utils.handle_thing)
        finally:
            sys.modules.pop(later.__name__, None)

    def test_leaves_the_other_handlers_alone(self):
        handlers.wrap(self.utils, "handle_thing", self.marking("a"), "a")
        self.assertEqual("handle_other", self.module.PAGE_HANDLERS[1].__name__)

    def test_a_helper_in_no_list_is_still_wrapped_on_the_module(self):
        self.utils.select_card = named("select_card")
        handlers.wrap(self.utils, "select_card", self.marking("a"), "a")
        self.assertEqual("select_card", self.utils.select_card.__name__)
        self.assertEqual(["handle_thing", "handle_other"], [h.__name__ for h in self.module.PAGE_HANDLERS])

    def test_a_missing_function_is_skipped(self):
        handlers.wrap(self.utils, "not_there", self.marking("a"), "a")
        self.assertFalse(hasattr(self.utils, "not_there"))


if __name__ == "__main__":
    unittest.main()
