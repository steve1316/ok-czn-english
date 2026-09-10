"""Check that upstream still has every name the fork patches.

A rename in `ok_tasks/` does not fail loudly. `handlers.wrap` returns at `if current is None`, `replace`
changes nothing and logs nothing above INFO, and the patch simply stops existing. The run then behaves like
stock upstream, which on the Global client means the fork's whole reason for existing is gone.

Nothing else in the suite would notice. Every other test builds a `types.SimpleNamespace` stand-in for the
task modules, and a stand-in is built carrying whatever name the fork asked for, so it can never catch a
rename. These run against the real modules instead.

This is its own file rather than part of `TestPatchComposition` because `handlers.each_list` finds handler
lists by scanning `sys.modules`. Importing the real modes here would put them in front of that file's seam
tests, which count the lists they change.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils  # noqa: E402
import utils_chaos  # noqa: E402
import utils_sortie  # noqa: E402
import utils_story  # noqa: E402

# Every name the fork reaches for, and the module that has to carry it. Handlers it wraps or replaces, helpers
# it swaps with `standing_in`, and the few it calls outright.
UPSTREAM_NAMES = {
    "utils": (
        "_current_equipment_for_slot", "_equipment_priority", "_equipment_state", "_find_member_level_tags",
        "_get_card_list", "_get_config_value", "_get_current_credit", "_get_game_text", "_member_deck_state",
        "_member_equipment_qualities", "_move_and_click", "_should_install_equipment", "find_box_at_point",
        "handle_card_assign", "handle_card_reward", "handle_confirm", "handle_equipment", "handle_event_task",
        "handle_expedition_result", "handle_negotiation", "handle_shop", "handle_stuck_log",
        "handle_view_original", "is_button_active", "is_frame_stuck", "is_subsequence", "log_node_status",
        "recognize_cards", "recognize_cards_in_deck", "recognize_event_options", "select_card",
    ),
    "utils_chaos": (
        "_move_and_click", "handle_archive_target_member", "handle_battle_auto_check", "handle_mask_card",
        "handle_save_target_member",
    ),
    "utils_sortie": (
        "_hand_card_names", "_hand_cards", "_is_card_name", "_read_hand_count", "_read_member_slots",
        "_try_all_card_keys", "handle_battle_page", "handle_get_card",
    ),
}

# Handlers the fork positions itself against by name, and the modes whose lists have to hold them. Being
# defined is not enough - `insert_before` and `append` find their place by walking `PAGE_HANDLERS`, so an
# anchor upstream stops registering leaves the fork's own handler installed nowhere.
ANCHORS_IN_LISTS = {
    "handle_archive_target_member": ("utils_chaos", "utils_sortie"),
    "handle_battle_auto_check": ("utils_chaos", "utils_story"),
    "handle_battle_page": ("utils_sortie",),
    "handle_card_assign": ("utils_chaos", "utils_sortie"),
    "handle_card_reward": ("utils_chaos", "utils_sortie"),
    "handle_confirm": ("utils_chaos", "utils_sortie", "utils_story"),
    "handle_equipment": ("utils_chaos", "utils_sortie"),
    "handle_event_task": ("utils_chaos", "utils_sortie"),
    "handle_expedition_result": ("utils_chaos", "utils_sortie"),
    "handle_get_card": ("utils_sortie",),
    "handle_mask_card": ("utils_chaos",),
    "handle_member_selection": ("utils_sortie",),
    "handle_negotiation": ("utils_chaos", "utils_sortie"),
    "handle_save_target_member": ("utils_chaos",),
    "handle_shop": ("utils_chaos", "utils_sortie"),
    "handle_stuck_log": ("utils_chaos", "utils_sortie"),
    "handle_view_original": ("utils_chaos", "utils_sortie"),
    "log_node_status": ("utils_chaos", "utils_sortie"),
}

MODULES = {"utils": utils, "utils_chaos": utils_chaos, "utils_sortie": utils_sortie, "utils_story": utils_story}


class TestUpstreamManifest(unittest.TestCase):

    def test_every_patched_name_is_still_there(self):
        for module_name, names in UPSTREAM_NAMES.items():
            for name in names:
                with self.subTest(module=module_name, name=name):
                    self.assertTrue(hasattr(MODULES[module_name], name), f"{module_name}.{name} is gone")

    def test_every_anchor_is_still_registered(self):
        for anchor, module_names in ANCHORS_IN_LISTS.items():
            for module_name in module_names:
                with self.subTest(anchor=anchor, mode=module_name):
                    registered = [handler.__name__ for handler in MODULES[module_name].PAGE_HANDLERS]
                    self.assertIn(anchor, registered, f"{module_name} no longer registers {anchor}")

    def test_the_framework_still_offers_the_hooks_every_install_rides(self):
        # `handlers.register` applies every list edit from `after_init`, and `load_config` carries the run-start
        # resets in stuck.py and notify.py. Lose either and the fork degrades to stock upstream in silence.
        from ok.task.task import BaseTask

        self.assertTrue(hasattr(BaseTask, "after_init"))
        self.assertTrue(hasattr(BaseTask, "load_config"))
