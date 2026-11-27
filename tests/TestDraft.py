"""Check which combatant the bot drafts for the team it has, and when it spends a reroll.

A reroll cannot be taken back, and a badge matched to the wrong card would rank every candidate wrongly, so
both the badge-to-card pairing and the spend condition are pinned here. So are the run's start screens: who the
Combatant List can pick, and which Risk Modifier each row reads as. Positions are the screens' own.
"""

import collections
import os
import sys
import tempfile
import types
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils_sortie  # noqa: E402

from tests.fakes import FakeBox as Box  # noqa: E402

from src.en import analysis, tested  # noqa: E402
from src.en.battle import PARTY  # noqa: E402
from src.en.dashboard import COMBATANTS, TEAM_GEAR  # noqa: E402
from src.en.handlers import insert_before  # noqa: E402
from src.en.draft import DRAFTED, ROLES, badges, choose, confirming_our_pick, drafting, rank, rerollable, role_for, role_of, wanted  # noqa: E402
from src.en.game_quality import COMBATANT_ROLE  # noqa: E402
from src.en.game_data import RISK_MODIFIERS  # noqa: E402
from src.en.sortie_loop import (HARDCORE_CLOSE, HARDCORE_SWITCH, HIGHER, KNOB_END, LIST_CLOSE, LOWER, MAX_STEPS, LEVEL_STATE, SLOT_CARD,  # noqa: E402
                                closing_list, drafted_pick, hardcore_handler, handle_send_coordinates, least_played, lobby_handler, modifier_rows, roster_only,
                                slot_check_handler)

WIDTH, HEIGHT = 1920, 1080
# Where the three cards sit, measured off the screen the run captured.
CARDS = (("Rin", 0.322), ("Beryl", 0.586), ("Magna", 0.851))
BADGE_Y, NAME_Y, REROLL_Y = 0.675, 0.724, 0.807
# The Lv.80 Risk Modifiers page as OCR read it on 2026-11-26, at the top of the list, with the Extended Modifiers panel on the right.
# The sixth row is cut off by the bottom edge, so it has no "+N Stages" yet.
RISK_PAGE = (
    ("Risk Modifiers", 0.146, 0.047), ("Modifier List", 0.084, 0.115), ("Time until list reset", 0.315, 0.115),
    ("Change Damage Amount taken by", 0.235, 0.210), ("monsters to 1 (1 time per battle)", 0.225, 0.245), ("+3 Stages", 0.427, 0.227),
    ("0", 0.506, 0.229), ("Stage 3 /30", 0.761, 0.322),
    ("Decrease Turn Draw by 1", 0.205, 0.378), ("+3 Stages", 0.427, 0.376),
    ("When a monster's HP drops to 30% or", 0.249, 0.510), ("+3 Stages", 0.426, 0.526), ("less, gain 2 Fortitude", 0.189, 0.545),
    ("Gradually decrease Shield Gain and Heal", 0.797, 0.535), ("Stage 0", 0.610, 0.554),
    ("Unable to recover Stress through Heals +4 Stages", 0.286, 0.675),
    ("On Ravage, unable to gain AP", 0.219, 0.827), ("+3 Stages", 0.427, 0.826),
    ("Increase all nrices in the Safe Zones and", 0.251, 0.943),
)


# The draft screen places its boxes by share of the screen.
FakeBox = partial(Box, width=80, height=26, units="fraction")


class FakeTask:
    """A task holding one OCR pass of the draft screen."""

    width, height = WIDTH, HEIGHT

    def __init__(self, boxes):
        self.all_texts = boxes

    def log_info(self, message):
        pass

    def sleep(self, seconds):
        pass


def draft_screen(roles=("Core", "攻击力", "Protection"), counters=("1/1", "1/1", "1/1")):
    """Build the draft screen as the reader sees it.

    Args:
        roles: The badge text on each card, left to right.
        counters: The reroll counter on each card, left to right.

    Returns:
        A `FakeTask`.
    """
    boxes = []
    for (name, x), role, counter in zip(CARDS, roles, counters):
        boxes.append(FakeBox(role, x, BADGE_Y))
        boxes.append(FakeBox(name, x, NAME_Y))
        boxes.append(FakeBox(counter, x + 0.013, REROLL_Y))
    return FakeTask(boxes)


def slot(name, x):
    """Build the slot dict `_read_member_slots` produces.

    Args:
        name: The candidate's name.
        x: The name box's centre.

    Returns:
        The slot dict.
    """
    return {"name": name, "x": x, "y": NAME_Y, "refresh_y": REROLL_Y}


class TestDraft(unittest.TestCase):

    def test_the_badge_readings_are_recognised(self):
        self.assertEqual("Core", role_of("Core"))
        self.assertEqual("Protection", role_of("Protection"))

    def test_the_rewritten_attack_badge_is_recognised(self):
        """The catalog rewrites Attack to 攻击力 for the card type label, and the badge shares the word."""
        self.assertEqual("Attack", role_of("攻击力"))
        self.assertEqual("Attack", role_of("Attack"))

    def test_text_that_is_not_a_badge_is_ignored(self):
        for text in ("Rin", "1/1", "LV", "", None):
            with self.subTest(text=text):
                self.assertIsNone(role_of(text))

    def test_each_badge_belongs_to_its_own_card(self):
        """Pairing a badge with the wrong card would rank all three wrongly."""
        task = draft_screen()
        found = badges(task)
        paired = {name: role_for(slot(name, x), found) for name, x in CARDS}
        self.assertEqual({"Rin": "Core", "Beryl": "Attack", "Magna": "Protection"}, paired)

    def test_an_unread_badge_ranks_last(self):
        """A card whose badge did not read must never outrank one that did."""
        self.assertGreater(rank(None), rank("Protection"))

    def test_the_best_of_the_real_draft_is_the_core(self):
        task = draft_screen()
        found = badges(task)
        best = min(CARDS, key=lambda card: rank(role_for(slot(*card), found)))
        self.assertEqual("Rin", best[0])

    def test_the_team_drafts_the_role_it_lacks(self):
        """A second damage dealer is only a fallback once the rerolls are spent."""
        cases = [
            # (team, offers, can reroll, expected pick or None for a reroll)
            # The second pick rerolls for a Healer, then settles for a Protector or Supporter before more damage.
            ({"Hugo"}, ("Khalipe", "Mika", "Cassius"), True, "Mika"),
            ({"Hugo"}, ("Beryl", "Hilde", "Khalipe"), True, None),
            ({"Hugo"}, ("Rin", "Cassius", "Khalipe"), False, "Khalipe"),
            # One Healer, Protector or Supporter fills the support slot, so the team goes back to damage.
            ({"Hugo", "Mika"}, ("Cassius", "Khalipe", "Rin"), True, "Rin"),
            # A Protector or Supporter leaves the team without healing, so the third pick takes a Healer on offer.
            ({"Hugo", "Cassius"}, ("Mika", "Khalipe", "Rin"), True, "Mika"),
            ({"Hugo", "Khalipe"}, ("Rin", "Tiphera", "Beryl"), True, "Tiphera"),
            # It never rerolls to find one: damage is taken instead.
            ({"Hugo", "Khalipe"}, ("Rin", "Cassius", "Beryl"), True, "Rin"),
            ({"Hugo", "Mika", "Khalipe"}, ("Tiphera", "Rin", "Beryl"), True, "Rin"),
            ({"Hugo"}, ("Beryl", "Rin", "Hilde"), True, None),
            ({"Hugo"}, ("Beryl", "Rin", "Hilde"), False, "Rin"),
            ({"Mika"}, ("Khalipe", "Beryl", "Cassius"), True, "Beryl"),
            (set(), ("Khalipe", "Beryl", "Rin"), True, "Rin"),
            # Live, the fourth pick wanted the Support the team lacked and rerolled all three offers away.
            ({"Maribell", "Rei", "Tenebria"}, ("Arabella", "Diana", "Olga"), True, "Arabella"),
            ({"Maribell", "Rei", "Tenebria"}, ("Veronica", "Diana", "Khalipe"), True, "Diana"),
        ]
        for party, offers, can_reroll, expected in cases:
            with self.subTest(party=party, offers=offers, can_reroll=can_reroll):
                pick = choose([COMBATANT_ROLE[name] for name in offers], wanted(party), can_reroll)
                self.assertEqual(expected, None if pick is None else offers[pick])

    def test_draft_least_played_outranks_the_role_the_team_lacks(self):
        """A kit test run wants every combatant's cards played live, so coverage outranks the role the team lacks."""
        cases = [
            # (offers, card plays so far, can reroll, expected pick or None for a reroll)
            (("Khalipe", "Rin", "Mika"), (56, 117, 0), True, "Mika"),
            (("Khalipe", "Rin", "Hugo"), (56, 117, 67), True, None),
            (("Khalipe", "Rin", "Hugo"), (56, 117, 67), False, "Khalipe"),
            # Two who have never played: the one the team wants goes first.
            (("Mika", "Luke", "Rin"), (0, 0, 117), True, "Luke"),
        ]
        for offers, played, can_reroll, expected in cases:
            with self.subTest(offers=offers, played=played, can_reroll=can_reroll):
                pick = choose([COMBATANT_ROLE[name] for name in offers], wanted({"Cassius"}), can_reroll, list(played))
                self.assertEqual(expected, None if pick is None else offers[pick])

    def test_a_card_played_counts_toward_its_owner_across_runs(self):
        """A tally that stops counting would draft the same untested-looking combatant every run."""
        with (tempfile.TemporaryDirectory() as folder, mock.patch.object(tested, "FILE", os.path.join(folder, "plays.json")),
              mock.patch.object(analysis, "drafting_least_played", lambda: True), mock.patch.object(tested, "_plays", None)):
            tested.played("Flash Slash")
            tested.played("Impulse")
            tested._plays = None
            self.assertEqual({"Yuki": 1}, dict(tested.plays()), "Impulse belongs to no one, Flash Slash is Yuki's")
        with mock.patch.object(analysis, "drafting_least_played", lambda: False):
            self.assertIsNone(tested.plays(), "with the switch off the draft goes by role")

    def test_confirm_waits_for_the_draft_to_pick(self):
        """A card still highlighted from before a restart was confirmed without the draft ever seeing the screen."""
        prompt = [types.SimpleNamespace(name="请选择加入的主战员")]
        utils = types.SimpleNamespace(find_box_at_point=lambda task, x, y: prompt[0], _get_game_text=lambda task, text: text,
                                      _get_card_list=lambda task, key: [])
        utils_sortie = types.SimpleNamespace(_read_member_slots=lambda task: [slot(name, x) for name, x in CARDS])
        confirmed = []
        handle_confirm = confirming_our_pick(lambda task: confirmed.append(True) or True, utils, utils_sortie)
        task = types.SimpleNamespace(node_status={})

        self.assertFalse(handle_confirm(task))
        task.node_status[DRAFTED] = "Magna"
        self.assertTrue(handle_confirm(task))
        # Off the draft screen, Confirm is upstream's as before.
        prompt[0] = None
        task.node_status = {}
        self.assertTrue(handle_confirm(task))
        self.assertEqual(2, len(confirmed))

    def test_a_pick_whose_confirm_did_not_take_is_picked_again(self):
        """Live, Mika's Confirm did not take, so the next pass counted her as joined and took Chizuru instead."""
        screen = draft_screen(roles=("Healing", "攻击力", "攻击力"), counters=("0/1", "0/1", "0/1"))
        offered = [slot(name, x) for name, (_, x) in zip(("Mika", "Chizuru", "Luke"), CARDS)]
        utils = types.SimpleNamespace(find_box_at_point=lambda task, x, y: types.SimpleNamespace(name="请选择加入的主战员"),
                                      _get_game_text=lambda task, text: text, _get_card_list=lambda task, key: [],
                                      _move_and_click=lambda task, x, y: None)
        handle_member_draft = drafting(utils, types.SimpleNamespace(_read_member_slots=lambda task: offered))
        task = types.SimpleNamespace(width=WIDTH, height=HEIGHT, all_texts=screen.all_texts, node_status={}, info={},
                                     log_info=lambda message: None, sleep=lambda seconds: None)
        task.info_set = task.info.__setitem__
        setattr(task, PARTY, frozenset({"Owen", "Hugo"}))
        setattr(task, TEAM_GEAR, "Legend/Legend/Legend, -/-/-")

        for _ in range(2):
            self.assertTrue(handle_member_draft(task))
        self.assertEqual("Mika", task.node_status[DRAFTED])
        self.assertEqual("Hugo, Owen, Mika", task.info[COMBATANTS])
        self.assertEqual("Legend/Legend/Legend, -/-/-, -/-/-", getattr(task, TEAM_GEAR))

    def test_a_pick_moved_out_of_its_row_stands(self):
        """Live, Renoa's card opened a details panel once clicked, the slot reader lost her, and the next pass drafted Tressa over her."""
        offered = [slot("Beryl", 0.472), slot("Tressa", 0.744)]
        utils = types.SimpleNamespace(find_box_at_point=lambda task, x, y: types.SimpleNamespace(name="请选择加入的主战员"),
                                      _get_game_text=lambda task, text: text, _get_card_list=lambda task, key: [],
                                      _move_and_click=lambda task, x, y: self.fail("drafted again"))
        utils_sortie = types.SimpleNamespace(_read_member_slots=lambda task: offered)
        confirmed = []
        task = types.SimpleNamespace(width=WIDTH, height=HEIGHT, node_status={DRAFTED: "Renoa"}, log_info=lambda message: None,
                                     all_texts=[FakeBox("Renoa", 0.239, 0.723), FakeBox("Beryl", 0.657, 0.725), FakeBox("Tressa", 0.922, 0.723)])
        self.assertFalse(drafting(utils, utils_sortie)(task))
        self.assertTrue(confirming_our_pick(lambda task: confirmed.append(True) or True, utils, utils_sortie)(task))
        self.assertEqual([True], confirmed)

    def test_every_role_in_the_data_is_one_the_draft_ranks(self):
        """A patch renaming a role would rank that whole role below an unread badge."""
        self.assertLessEqual(set(COMBATANT_ROLE.values()), set(ROLES))

    def test_an_unspent_slot_can_be_rerolled(self):
        task = draft_screen()
        self.assertTrue(all(rerollable(task, slot(name, x)) for name, x in CARDS))

    def test_a_spent_slot_is_never_rerolled_again(self):
        """The counter reads 0/1 once used, and clicking it again would waste a frame every pass."""
        task = draft_screen(counters=("0/1", "1/1", "0/1"))
        spent = [name for name, x in CARDS if not rerollable(task, slot(name, x))]
        self.assertEqual(["Rin", "Magna"], spent)

    def test_a_slot_with_no_reroll_button_is_never_rerolled(self):
        task = draft_screen()
        no_button = {"name": "Rin", "x": 0.322, "y": NAME_Y, "refresh_y": None}
        self.assertFalse(rerollable(task, no_button))



class FakeListTask(FakeTask):
    """A task holding one OCR pass of the Combatant List, with the debug log upstream's reader writes to."""

    def log_debug(self, message):
        pass


class FakeScrollingListTask(FakeListTask):
    """A task on the Combatant List whose OCR moves to the next page on every scroll, recording the names it tapped."""

    def __init__(self, pages):
        super().__init__(pages[0])
        self.pages = list(pages[1:])
        self.tapped = []

    def click_box(self, box):
        self.tapped.append(box.name)

    def move_relative(self, x, y):
        pass

    def scroll_relative(self, x, y, amount):
        pass

    def ocr(self):
        return self.pages.pop(0) if self.pages else []


class FakeFormationTask(FakeTask):
    """A task on the Combatant Formation or the Hardcore Mode notice, with the switch's "on" end a given share white."""

    def __init__(self, title, knob):
        super().__init__([FakeBox(title, 0.13, 0.043)])
        self.node_status = {}
        self.frame = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
        left, top, right, bottom = KNOB_END
        x0, x1 = int(left * WIDTH), int(right * WIDTH)
        self.frame[int(top * HEIGHT):int(bottom * HEIGHT), x0:x0 + round((x1 - x0) * knob)] = 255


class FakeLobbyTask(FakeTask):
    """A task on the Sortie lobby, recording what it pressed and whether it stopped."""

    name = "SortieMode"

    def __init__(self, level):
        super().__init__([FakeBox("Cumulative Sortie Clears", 0.111, 0.244), FakeBox(level, 0.499, 0.457), FakeBox("进入", 0.499, 0.901)])
        self.node_status = {}
        self.pressed = []
        self.stopped = False

    def click_box(self, box):
        self.pressed.append(box.name)

    def disable(self):
        self.stopped = True

    def notification(self, message, title=None, tray=False):
        pass


def lobby_utils(pick, taps):
    """Stand in for upstream's `utils` on the lobby: the Sortie Level setting, the tap and the run reset."""
    return types.SimpleNamespace(_get_config_value=lambda task, key, default: pick, _move_and_click=lambda task, x, y: taps.append((x, y)),
                                 reset_mission_status=lambda task: None)


class TestRunStart(unittest.TestCase):
    """What the start of a Sortie run reads: the lobby's tier, the Combatant List's names and the Risk Modifiers rows."""

    def test_the_combatant_list_offers_only_real_names(self):
        # Upstream's own reader, so a rename there shows up here. Its random fallback once could tap any of these labels.
        names = ("Rin", "等级", "攻击力", "Car", "Q", "Lv.60 Nia")
        task = FakeListTask([FakeBox(name, 0.20 + 0.12 * index, 0.40) for index, name in enumerate(names)])
        with mock.patch.object(tested, "plays", return_value=None):
            boxes = roster_only(utils_sortie._battle_member_boxes)(task)
        self.assertEqual(["Rin", "Lv.60 Nia"], [box.name for box in boxes])

    def test_draft_least_played_narrows_the_list_to_the_least_played(self):
        boxes = [FakeBox(name, 0.2, 0.4) for name in ("Rin", "Nia", "Magna")]
        with mock.patch.object(tested, "plays", return_value=collections.Counter({"Rin": 4, "Nia": 0, "Magna": 0})):
            self.assertEqual(["Nia", "Magna"], [box.name for box in least_played(boxes)])
        with mock.patch.object(tested, "plays", return_value=None):
            self.assertEqual(boxes, least_played(boxes))

    def test_the_drafted_pick_assigns_that_combatant_or_the_game_s_own(self):
        # Auto must never tap a name, since the game has already picked the red Drafted Combatant. A named pick off the first page is scrolled
        # to, and one missing from the list falls back to Assign rather than upstream's random tap.
        pages = ([FakeBox("Rita", 0.22, 0.49), FakeBox("Amir", 0.80, 0.49)], [FakeBox("Nia", 0.36, 0.49), FakeBox("Mei Lin", 0.645, 0.49)])
        for pick, plays, tapped, upstream in (("Auto", None, [], False), ("Nia", None, ["Nia"], False), ("Mei Lin", None, ["Mei Lin"], False),
                                              ("Rin", None, [], False), ("Auto", collections.Counter(), [], True)):
            with self.subTest(pick=pick, plays=plays):
                task, calls = FakeScrollingListTask(pages), []
                utils = types.SimpleNamespace(_get_config_value=lambda task, key, default: pick, _simplify_texts=lambda texts: texts)
                upstream_sortie = types.SimpleNamespace(_confirm_battle_member_selection=lambda task: calls.append("assign") or True)
                select = drafted_pick(utils, upstream_sortie)(lambda task, max_scrolls: calls.append("upstream") or True)
                with mock.patch.object(tested, "plays", return_value=plays):
                    self.assertTrue(select(task))
                self.assertEqual(tapped, task.tapped)
                self.assertEqual(["upstream"] if upstream else ["assign"], calls)

    def test_the_list_has_closed_before_the_next_frame(self):
        # Upstream's own confirm, so a rename shows up here. It presses Back with the pick already in the slot, as the once-per-run check does.
        # Without the wait, the next frame still saw the list and tapped the pick again, which cancelled the Back.
        events = []
        task = FakeListTask([])
        task.sleep = lambda seconds: events.append(("sleep", seconds))
        with mock.patch.object(utils_sortie, "calculate_dominant_hue", return_value=-1), \
                mock.patch.object(utils_sortie, "_move_and_click", side_effect=lambda task, x, y: events.append(("tap", x, y))):
            self.assertTrue(closing_list(utils_sortie._confirm_battle_member_selection)(task))
        self.assertEqual([("tap", 0.044, 0.050), ("sleep", LIST_CLOSE)], events)

    def test_a_filled_slot_is_checked_once_against_a_named_pick(self):
        # Auto keeps whoever fills the slot, and an empty slot is upstream's to open. Reopening every frame would never let the run start.
        for pick, role, checked, taps in (("Rita", "攻击力", False, [SLOT_CARD]), ("Auto", "攻击力", False, []), ("Rita", None, False, []),
                                          ("Rita", "攻击力", True, [])):
            with self.subTest(pick=pick, role=role, checked=checked):
                task, tapped = FakeFormationTask("主战员配置", 0), []
                if role:
                    task.all_texts.append(FakeBox(role, 0.178, 0.799))
                task.node_status["_en_slot_checked"] = checked
                utils = types.SimpleNamespace(_get_config_value=lambda task, key, default: pick, _move_and_click=lambda task, x, y: tapped.append((x, y)))
                self.assertEqual(bool(taps), slot_check_handler(utils)(task))
                self.assertEqual(taps, tapped)

    def test_hardcore_mode_is_switched_to_the_setting(self):
        # The white knob sits at the track's right end while on. A knob mid-slide must never tap, or it would flip a switch already on its way.
        for title, wanted, knob, taps in (("主战员配置", True, 0, [HARDCORE_SWITCH]), ("主战员配置", False, 1, [HARDCORE_SWITCH]),
                                          ("主战员配置", True, 1, []), ("主战员配置", False, 0, []), ("主战员配置", True, 0.3, []),
                                          ("Hardcore Mode", True, 1, [HARDCORE_CLOSE])):
            with self.subTest(title=title, wanted=wanted, knob=knob):
                task, tapped = FakeFormationTask(title, knob), []
                utils = types.SimpleNamespace(_get_config_value=lambda task, key, default: wanted, _move_and_click=lambda task, x, y: tapped.append((x, y)))
                self.assertEqual(bool(taps), hardcore_handler(utils)(task))
                self.assertEqual(taps, tapped)

    def test_the_lobby_steps_toward_the_picked_level_before_entering(self):
        # A wrong direction walks away from the pick until the step cap stops the run.
        for level, pick, tap in (("LV.50", "Lv.80", HIGHER), ("Lv.60", "Lv.40", LOWER), ("LV.65", "Lv.65", None), ("LV.80", "Keep current", None)):
            with self.subTest(level=level, pick=pick):
                task, taps = FakeLobbyTask(level), []
                self.assertTrue(lobby_handler(lobby_utils(pick, taps))(task))
                self.assertEqual([tap] if tap else [], taps)
                self.assertEqual([] if tap else ["进入"], task.pressed)

    def test_send_coordinates_is_pressed_ahead_of_the_battle_reader(self):
        # The battle reader takes this frame for a battle with an empty hand, so Send Coordinates has to be pressed ahead of it.
        task = FakeLobbyTask("")
        task.all_texts = [FakeBox(text, x, y) for text, x, y in (("1995/2924", 0.213, 0.039), ("BATTLE", 0.032, 0.457),
                                                                  ("END", 0.032, 0.477), ("Send Coordinates", 0.906, 0.916))]
        self.assertTrue(handle_send_coordinates(task))
        self.assertEqual(["Send Coordinates"], task.pressed)
        with mock.patch.object(utils_sortie, "PAGE_HANDLERS", list(utils_sortie.PAGE_HANDLERS)):
            insert_before("handle_expedition_result", handle_send_coordinates, only=("utils_sortie",))
            names = [handler.__name__ for handler in utils_sortie.PAGE_HANDLERS]
        self.assertLess(names.index("handle_send_coordinates"), names.index("handle_battle_page"))

    def test_a_level_the_arrows_never_reach_stops_the_run(self):
        task, taps = FakeLobbyTask("LV.65"), []
        task.node_status[LEVEL_STATE] = MAX_STEPS
        lobby_handler(lobby_utils("Lv.80", taps))(task)
        self.assertTrue(task.stopped)
        self.assertEqual(([], []), (taps, task.pressed))

    def test_each_risk_modifier_row_reads_as_its_modifier(self):
        rows = modifier_rows([FakeBox(text, x, y) for text, x, y in RISK_PAGE], WIDTH, HEIGHT)
        self.assertEqual(list(RISK_MODIFIERS)[:5], [name for name, _ in rows])
        for (name, y), wanted in zip(rows, (0.227, 0.376, 0.526, 0.675, 0.826)):
            with self.subTest(name=name):
                self.assertAlmostEqual(wanted, y, places=2)

    def test_a_misread_row_still_beats_the_other_modifier_of_its_cost(self):
        # Both five-stage rows wrap, and OCR dropped a letter from this one.
        lines = (("Increase all nrices in the Safe Zones and", 0.25, 0.43), ("the Dellang Shop by 30% and additionally", 0.25, 0.46),
                 ("increase the price of Flash by 100%", 0.22, 0.49), ("+5 Stages", 0.427, 0.46))
        rows = modifier_rows([FakeBox(text, x, y) for text, x, y in lines], WIDTH, HEIGHT)
        self.assertEqual([list(RISK_MODIFIERS)[5]], [name for name, _ in rows])


if __name__ == "__main__":
    unittest.main()
