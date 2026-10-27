"""Check what the picker does with a hand once a turn is under way.

`cards.py` decides what a hand is worth. This is the layer above it: which card actually gets a key pressed
for it, what happens when the game refuses one, and when a turn should just be ended.
"""

import json
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

# The real module, for a prompt the fork runs unchanged over a different reading of the screen.
import utils_sortie as real_sortie  # noqa: E402

from src.en import battle, board, cards, ego, overrides  # noqa: E402
from src.en.handlers import standing_in  # noqa: E402
from tests.TestBoard import FakeTask, flat, paint, paint_enemy, pasted  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

# Haru is Justice and Renoa is Void, and these two cards are otherwise identical: one Action Point, an
# Attack, exactly "100% Damage". So only a weakness read off the screen can order them.
ATTACK = "Anchor"
VOID_ATTACK = "Annihilation Shot"
BIG_ATTACK = "Charge Launcher"
CURSE = "Anemia"
# A neutral 1-point Skill that only shields.
SHIELD = "Barrier Utilization"
# One Ego of each kind, as the planner would have read them off their previews.
GUARD_EGO = ego.Ego("Legato of Faith", frozenset({ego.GUARD}), "")
STRIKE_EGO = ego.Ego("Execution", frozenset({ego.STRIKE}), "")
SETUP_EGO = ego.Ego("Tactical Command", frozenset({ego.SETUP}), "")

# Where the painted enemy stands. Anywhere inside the band the counters are looked for in will do.
ENEMY_AT = (0.50, 0.25)
# The game's check when a turn is ended with a card it would still take, with its Cancel and Confirm buttons.
CARDS_LEFT_PROMPT = (FakeBox("Cards in your hand can still be used.", 0.5, 0.36, width=600),
                     FakeBox("取消", 0.34, 0.60), FakeBox("确认", 0.67, 0.60))


def hand(*names_in_order, keyless=(), at=None):
    """Build a hand the way `_hand_cards` hands one over.

    Args:
        names_in_order: Card names, left to right as they sit on screen.
        keyless: Names whose hotkey the reader failed to pair up, so they cannot be played.
        at: Left edges of the names as screen fractions, for a hand read short of the counter. Spread evenly
            when not given, since only the order matters to a hand read in full.

    Returns:
        A list of hand-card dicts.
    """
    at = at or [0.2 + 0.1 * index for index in range(len(names_in_order))]
    return [{"name": name, "key": None if name in keyless else str(index + 1), "left_x": left_x}
            for index, (name, left_x) in enumerate(zip(names_in_order, at))]


def handlers_of(module):
    """Index a mode's page handlers by name.

    Args:
        module: The upstream mode module whose `PAGE_HANDLERS` list is read.

    Returns:
        A dict of handler name to handler.
    """
    return {getattr(handler, "__name__", None): handler for handler in module.PAGE_HANDLERS}


@contextmanager
def counting(module, name):
    """Count the calls to one function while still letting it do its real work.

    Args:
        module: The module the function is looked up on.
        name: Its name there.

    Yields:
        A list that gains an entry per call.
    """
    real = getattr(module, name)
    calls = []

    def counted(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    setattr(module, name, counted)
    try:
        yield calls
    finally:
        setattr(module, name, real)


class TestChoosing(unittest.TestCase):
    """Which card gets played, given what the turn has already learnt."""

    def test_the_best_card_is_chosen(self):
        chosen = battle.choose(hand(ATTACK, BIG_ATTACK), cards.Board(), set())
        self.assertEqual(chosen["name"], BIG_ATTACK)

    def test_a_refused_card_is_passed_over(self):
        # The game would not play it earlier in this turn, so trying it again only wastes the frame.
        chosen = battle.choose(hand(ATTACK, BIG_ATTACK), cards.Board(), {BIG_ATTACK})
        self.assertEqual(chosen["name"], ATTACK)

    def test_a_card_with_no_hotkey_is_passed_over(self):
        # There is no way to press a key the reader never found.
        chosen = battle.choose(hand(BIG_ATTACK, ATTACK, keyless=(BIG_ATTACK,)), cards.Board(), set())
        self.assertEqual(chosen["name"], ATTACK)

    def test_nothing_left_ends_the_turn(self):
        self.assertIsNone(battle.choose(hand(ATTACK), cards.Board(), {ATTACK}))

    def test_a_hand_of_curses_ends_the_turn(self):
        self.assertIsNone(battle.choose(hand(CURSE), cards.Board(), set()))

    def test_spare_points_clear_a_card_that_hurts_while_held(self):
        # Live: three Bleeds sat out turn after turn with all three points unspent. Bleed deals damage, so it goes
        # ahead of Parasitic Spores. Abyssal Erosion hurts through its Retain line, but costs 4.
        for held, points, cleared in ((("Parasitic Spores", "Bleed"), 3, "Bleed"), (("Abyssal Erosion",), 3, None),
                                      (("Abyssal Erosion",), 4, "Abyssal Erosion")):
            with self.subTest(held=held, points=points):
                chosen = battle.choose(hand(*held), cards.Board(action_points=points), set())
                self.assertEqual(cleared, chosen and chosen["name"])

    def test_an_empty_hand_ends_the_turn(self):
        self.assertIsNone(battle.choose([], cards.Board(), set()))

    def test_an_invulnerable_enemy_is_not_attacked(self):
        # Damage is wasted while it cannot lose Health, so attacks stay in hand and the turn ends once the shields are played.
        invulnerable = cards.Board(invulnerable=True)
        for held, played in (((ATTACK, BIG_ATTACK), None), ((ATTACK, SHIELD), SHIELD)):
            with self.subTest(held=held):
                chosen = battle.choose(hand(*held), invulnerable, set())
                self.assertEqual(played, chosen and chosen["name"])


class Previewed:
    """A task whose screen shows an Ego's preview card once its key is pressed."""

    def __init__(self, boxes):
        self.boxes = boxes
        self.all_texts = []
        self.width, self.height = 1920, 1080
        self.executor = types.SimpleNamespace(ocr_po_translation=None)
        self.clicked = []

    def send_key(self, key):
        pass

    def sleep(self, seconds):
        pass

    def ocr(self, box=None):
        return self.boxes

    def click_box(self, box):
        self.clicked.append(box)


class TestEgoPlanner(unittest.TestCase):
    """Which Ego a turn fires, from what the screen says about the fight."""

    def test_roles_come_from_the_preview_text(self):
        # Morale's "Damage Amount" is a buff, not damage, which is the misreading that would fire a buff as a strike.
        for text, roles in (("Heal 140% Activate the Retain effect of all of Orlea's cards in hand", {ego.GUARD}),
                            ("Gain 2 Morale and 1 Fortitude for 1 turn", {ego.SETUP}),
                            ("Morale +100% Damage Amount", {ego.SETUP}),
                            ("Deal 300% Damage to all enemies", {ego.STRIKE}),
                            ("Gain 120% Shield. Draw 1 card", {ego.GUARD, ego.SETUP})):
            with self.subTest(text=text):
                self.assertEqual(ego.roles_of(text), roles)

    def test_a_learnt_ego_is_known_to_the_next_run(self):
        # The point of saving them: a restart must not preview every Ego again.
        mark = np.linspace(-1, 1, 128, dtype=np.float32)
        mark /= np.linalg.norm(mark)
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(ego, "EGO_FILE", str(Path(folder) / "data" / "egos.json")), \
                mock.patch.object(ego, "_known", None):
            ego.learn(mark, ego.Ego("Legato of Faith", ego.roles_of("Heal 140%"), "Heal 140%"))
            ego._known = None
            self.assertEqual(ego.recall(ego.known(), mark), GUARD_EGO._replace(text="Heal 140%"))

    def test_both_kinds_of_preview_card_read(self):
        # Combatant Egos label their card "Ego Skill" where partners say "Partners". Laid out as Legato of Faith's card measured.
        for label, name in (("Partners", "Legato of Faith"), ("Ego Skil", "Reflection: Zero")):
            with self.subTest(label=label):
                task = Previewed([FakeBox(name, 0.480, 0.479, width=300), FakeBox(label, 0.466, 0.517, width=150),
                                  FakeBox("Heal140%", 0.453, 0.574, width=150), FakeBox("all of Orlea's cards in hand", 0.509, 0.644, width=450),
                                  FakeBox("Wound", 0.587, 0.857), FakeBox("Cancel", 0.105, 0.728)])
                read = ego.identify(task, types.SimpleNamespace(), "F1")
                self.assertEqual((read.name, read.text, read.roles), (name, "Heal140% all of Orlea's cards in hand", {ego.GUARD}))

    def test_the_first_rule_that_applies_wins(self):
        every = [("F1", GUARD_EGO, True), ("F2", STRIKE_EGO, True), ("F3", SETUP_EGO, True)]
        cases = (
            # (name, slots, banked, after_hit, invulnerable, attacking, boss, fired)
            ("a hit the team cannot take", every, 3, 0.2, False, True, False, "F1"),
            ("a full bar on a healthy team", every, 7, 0.9, False, True, False, "F2"),
            ("a full bar on a hurt team", every, 7, 0.4, False, True, False, "F1"),
            ("a full bar into invulnerability", every[1:], 7, 0.9, True, True, False, "F3"),
            ("invulnerable short of a full bar", every[1:], 3, 0.9, True, True, False, None),
            ("a set-up ahead of the attacks", every, 3, 0.9, False, True, False, "F3"),
            ("no attacks to set up", every, 3, 0.9, False, False, False, None),
            ("a boss saving for its strike", [("F2", STRIKE_EGO, False), ("F3", SETUP_EGO, True)], 3, 0.9, False, True, True, None),
            ("an unaffordable guard", [("F1", GUARD_EGO, False), ("F3", SETUP_EGO, True)], 3, 0.2, False, True, False, "F3"),
            ("an Ego never read", [("F1", None, True)], 7, 0.2, False, True, False, None),
        )
        for name, slots, banked, after_hit, invulnerable, attacking, boss, fired in cases:
            with self.subTest(name):
                choice = ego.decide(slots, banked, after_hit, invulnerable, attacking, boss)
                self.assertEqual(fired, choice and choice[0])


class TestTurnTracking(unittest.TestCase):
    """Telling a card the game would not play apart from one it did, and both apart from a fresh turn."""

    def test_a_card_still_in_hand_was_refused(self):
        # Counting the whole hand is not enough: a card that draws replaces itself, so the hand size can be
        # unchanged on a card that played perfectly well. How many of that one card are left does answer it.
        self.assertTrue(battle.was_refused(ATTACK, 1, [ATTACK, BIG_ATTACK]))

    def test_a_card_gone_from_hand_was_played(self):
        self.assertFalse(battle.was_refused(ATTACK, 1, [BIG_ATTACK]))

    def test_a_card_that_drew_another_is_not_a_refusal(self):
        self.assertFalse(battle.was_refused(ATTACK, 1, [BIG_ATTACK, CURSE]))

    def test_another_copy_of_the_same_card_is_not_a_refusal(self):
        # A deck holds several copies of a card, so a hand can too. One of three going down to two is the
        # game accepting it, not refusing it - reading that as a refusal stranded the other two.
        self.assertFalse(battle.was_refused(ATTACK, 3, [ATTACK, ATTACK]))

    def test_the_last_copy_staying_put_is_a_refusal(self):
        self.assertTrue(battle.was_refused(ATTACK, 2, [ATTACK, ATTACK]))

    def test_nothing_attempted_is_not_a_refusal(self):
        self.assertFalse(battle.was_refused(None, 0, [ATTACK]))

    def test_only_a_deal_after_end_turn_is_a_new_turn(self):
        for description, before, after, ended, expected in (
                ("a bigger hand after end turn", 1, 5, True, True),
                ("the same hand", 5, 5, True, False),
                ("a shrinking hand", 5, 4, True, False),
                ("the first frame of a battle", None, 5, False, True),
                # Luke's Stealth Reload adds bullets mid-turn, and Finisher Round counts what the turn has played.
                ("a hand grown by a card mid-turn", 4, 6, False, False),
        ):
            with self.subTest(description):
                self.assertEqual(battle.new_turn(before, after, ended), expected)


class Pressed:
    """A task that records what was sent to the game instead of sending it."""

    def __init__(self, hand_cards, smart=True, action_points=True, egos=(), weakness=None):
        self.hand_cards = hand_cards
        # What a template search for the Attack button finds. Nothing, unless a test puts the button up.
        self.attack_button = None
        self.clicked = []
        self.config = {overrides.SMART_CARD_PLAY: smart}
        # A fresh list per frame, the way `SortieMode.run` rebinds it after every OCR pass.
        self.all_texts = []
        # A flat frame is enough for the readout, which is judged on how much of it is lit, so white reads as
        # points remaining and black as none. The badges are painted on by the same helpers `TestBoard` uses.
        self.frame = flat(255 if action_points else 0)
        self.height, self.width = self.frame.shape[:2]
        if weakness:
            paint_enemy(self.frame, ENEMY_AT[0], ENEMY_AT[1], board.ATTRIBUTE_HUES[weakness])
        paint(self.frame, egos)
        self.keys = []
        self.logged = []
        # Where `_move_and_click` tapped, as screen fractions, and what a cropped read of the hand prompt's counter gives.
        self.taps = []
        self.progress = []

    def send_key(self, key):
        self.keys.append(key)

    def ocr(self, *region):
        return self.progress

    def box_of_screen(self, *region):
        return region

    def find_one(self, feature_name=None, box=None):
        return self.attack_button if feature_name == battle.START_ATTACK else None

    def find_feature(self, feature_name=None, box=None):
        # The end-turn button is never up, so the Ego planner leaves these frames to the picker and upstream.
        return []

    def click_box(self, box):
        self.clicked.append(box)

    def sleep(self, seconds):
        pass

    def log_info(self, message):
        self.logged.append(message)


@contextmanager
def upstream(hand_cards, smart=True, action_points=True, egos=(), weakness=None):
    """Stand the two upstream modules up in `sys.modules` so the install has something to patch.

    Args:
        hand_cards: What `_hand_cards` should report.
        smart: What the Smart Card Play setting reads as.
        action_points: Whether the Action Point readout should look lit.
        egos: Slot keys whose cost badge should look affordable.
        weakness: An attribute colour to draw on an enemy's badge, or None for no enemies at all.

    Yields:
        The fake `utils_sortie` module and the task the replacement is called with.
    """
    utils = types.ModuleType("utils")
    utils._get_config_value = lambda task, key, default: task.config.get(key, default)
    utils_sortie = types.ModuleType("utils_sortie")
    utils_sortie._hand_cards = lambda task: task.hand_cards
    # The counter, which a test reading the hand short of it sets on the task.
    utils_sortie._read_hand_count = lambda task: getattr(task, "counter", None) or len(task.hand_cards)
    utils_sortie._is_card_name = lambda name: True
    utils_sortie.find_box_at_point = real_sortie.find_box_at_point
    utils_sortie._move_and_click = lambda task, x, y: task.taps.append((round(x, 3), round(y, 3)))
    utils_sortie.name_reads = []
    utils_sortie._hand_card_names = lambda task: utils_sortie.name_reads.append(task.all_texts) or []
    utils_sortie.blind_calls = []
    utils_sortie._try_all_card_keys = lambda task, count: utils_sortie.blind_calls.append(count)
    utils_sortie.offered = []

    def choice(options):
        """Answer the way the real `random` would, recording what it was given to choose between.

        Args:
            options: What is being chosen between.

        Returns:
            One of them. Which one does not matter, but what was on offer does.
        """
        options = list(options)
        utils_sortie.offered.append(options)
        return options[0]

    utils_sortie.random = types.SimpleNamespace(choice=choice, uniform=lambda low, high: low)
    utils_sortie.asked = []

    def handle_battle_page(task):
        """Stand in for upstream's battle frame, putting `random` the questions upstream puts it.

        Asking here rather than afterwards is the point: what matters is what upstream's own call returns
        while the frame is running, not what the stand-in would say once it has been put back.

        Args:
            task: The task the frame is running against.
        """
        utils_sortie.asked.append({"ego": utils_sortie.random.choice(list(board.EGO_KEYS)),
                                   "other": utils_sortie.random.choice(["a", "b"]),
                                   "wait": utils_sortie.random.uniform(0.2, 0.8)})

    utils_sortie.handle_battle_page = handle_battle_page

    def handle_battle_hand_select(task):
        """Stand in for upstream's hand prompt, which clicks a box chosen at random from the hand.

        Args:
            task: The task whose `all_texts` holds the hand.
        """
        task.click_box(utils_sortie.random.choice(task.all_texts))

    utils_sortie.handle_battle_hand_select = handle_battle_hand_select
    utils_sortie.handle_return_to_draw_pile = types.SimpleNamespace(__name__="handle_return_to_draw_pile")
    # The seam edits this list rather than the module attribute, so the fake has to carry one too, with the anchor
    # the fork inserts its own handler in front of.
    utils_sortie.PAGE_HANDLERS = [handle_battle_page, handle_battle_hand_select, types.SimpleNamespace(__name__="handle_center_confirm")]
    saved = {name: sys.modules.get(name) for name in ("utils", "utils_sortie")}
    sys.modules["utils"], sys.modules["utils_sortie"] = utils, utils_sortie
    try:
        yield utils_sortie, Pressed(hand_cards, smart, action_points, egos, weakness)
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class TestInstalling(unittest.TestCase):
    """The patch itself. A replacement that silently fails to install would look exactly like working code."""

    def test_the_blind_fallback_is_replaced(self):
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            self.assertTrue(getattr(utils_sortie._try_all_card_keys, "_en_picker", False))

    def test_installing_again_does_not_wrap_the_replacement(self):
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            once = utils_sortie._try_all_card_keys
            battle.install()
            self.assertIs(utils_sortie._try_all_card_keys, once)

    def test_story_leaves_battles_to_auto_unless_it_is_locked(self):
        # Story's own handler only turns the game's Auto on, so a fight with Auto locked waited there for good.
        def handle_battle_auto_check_recording(task):
            return True

        confirm = types.SimpleNamespace(__name__="handle_center_confirm")
        utils_story = types.SimpleNamespace(PAGE_HANDLERS=[handle_battle_auto_check_recording, confirm])
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            # Story loads after the picker is in, and unseen its end-of-turn check confirmed a turn ended on an unread hand.
            with mock.patch.dict(sys.modules, utils_story=utils_story):
                battle.install()
                for _ in range(2):
                    battle.fight_story_battles()
            gate, picker, prompt, *_ = utils_story.PAGE_HANDLERS
            self.assertEqual([gate, picker, prompt, battle.handle_cards_left, confirm], utils_story.PAGE_HANDLERS)
            self.assertIsNot(picker, utils_sortie.handle_battle_page)
            self.assertIsNot(prompt, utils_sortie.handle_battle_hand_select)
            left, top, _, _ = battle.AUTO_BUTTON
            # A prompt shades the padlock too dim to read, so the fight has to be remembered from before it. Started on
            # the prompt, there is nothing to remember, and Auto's check would only wait on it.
            task = FakeTask(flat(0))
            for step, (crop, auto_plays) in enumerate((("story_auto_locked_dim", False), ("story_auto_on", True),
                                                       ("story_auto_locked_dim", True), ("story_auto_locked", False),
                                                       ("story_auto_locked_dim", False))):
                with self.subTest(step=step, crop=crop):
                    task.frame = pasted(crop, int(left * 1920), int(top * 1080))
                    self.assertEqual(auto_plays, gate(task))

    def test_the_chosen_card_gets_its_hotkey_pressed(self):
        with upstream(hand(ATTACK, BIG_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, len(task.hand_cards))
            # Charge Launcher is the better buy, and it is the second card, so key 2 then the confirm.
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY])

    def test_a_hand_of_curses_ends_the_turn(self):
        with upstream(hand(CURSE)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 1)
            self.assertEqual(task.keys, [battle.END_TURN_KEY])

    def test_switching_it_off_hands_back_to_upstream(self):
        with upstream(hand(ATTACK), smart=False) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 4)
            self.assertEqual(task.keys, [])
            self.assertEqual(utils_sortie.blind_calls, [4])

    def test_the_type_label_filter_is_taught_english(self):
        # Upstream's own filter lists only Chinese type labels, so on the Global client every English one
        # reached the hand as a card name.
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            battle.install()
            self.assertFalse(utils_sortie._is_card_name("Basic Attack"))
            self.assertFalse(utils_sortie._is_card_name("Status Ailm"))
            self.assertTrue(utils_sortie._is_card_name(ATTACK))

    def test_upstreams_own_chinese_labels_are_still_excluded(self):
        # The catalog rewrites some English labels into Chinese, and upstream's filter is what catches those.
        # Replacing its filter rather than wrapping it let "技能" and "基础技能" back into the hand.
        with upstream(hand(ATTACK)) as (utils_sortie, _):
            utils_sortie._is_card_name = lambda name: "技能" not in name
            battle.install()
            self.assertFalse(utils_sortie._is_card_name("技能"))
            self.assertFalse(utils_sortie._is_card_name("基础技能"))
            self.assertTrue(utils_sortie._is_card_name(ATTACK))

    def test_the_hand_is_only_read_once_for_one_ocr_pass(self):
        # Upstream reads the hand twice a frame and the picker would make it three. Each read logs a line per
        # box on screen, so on the busiest screen in the game that is the difference worth removing.
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._hand_card_names(task)
            utils_sortie._hand_card_names(task)
            self.assertEqual(len(utils_sortie.name_reads), 1)

    def test_the_next_ocr_pass_reads_the_hand_again(self):
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._hand_card_names(task)
            task.all_texts = []
            utils_sortie._hand_card_names(task)
            self.assertEqual(len(utils_sortie.name_reads), 2)

    def test_reading_the_hand_does_not_shout_every_box_at_the_log(self):
        # Upstream prints one line per box on screen from inside this read, plus two summaries - a debugging
        # aid for its own region filter, shipped at info level, and about a ninth of a day's log.
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            quiet_read = utils_sortie._hand_card_names

            def noisy_read(task_):
                task_.log_info("  OCR: box one")
                return quiet_read(task_)

            utils_sortie._hand_card_names = noisy_read
            battle.install()
            utils_sortie._hand_card_names(task)
            self.assertEqual([], task.logged)

    def test_an_empty_readout_ends_the_turn_without_trying_a_card(self):
        # Nothing in hand is free, and the readout says there is nothing left to spend, so trying each card
        # in turn only to be refused would cost several seconds a turn for an answer already on screen.
        with upstream(hand(ATTACK, BIG_ATTACK), action_points=False) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, [battle.END_TURN_KEY])

    def test_a_lit_readout_still_plays_a_card(self):
        with upstream(hand(ATTACK, BIG_ATTACK), action_points=True) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY])

    def test_the_attribute_the_enemies_are_weak_to_is_preferred(self):
        with upstream(hand(ATTACK, VOID_ATTACK), weakness="PURPLE") as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            # Renoa's card is the Void one, and it is second in hand, so key 2.
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY])

    def test_with_no_enemies_read_the_hand_order_stands(self):
        with upstream(hand(ATTACK, VOID_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, ["1", battle.CONFIRM_KEY])

    def test_the_weakness_is_read_once_a_turn(self):
        # It describes the fight rather than the frame, it costs a pass over a third of the screen, and a hit
        # landing over an enemy hides its badge for a frame or two.
        with upstream(hand(ATTACK, BIG_ATTACK), weakness="PURPLE") as (utils_sortie, task):
            battle.install()
            with counting(board, "weakness") as reads:
                utils_sortie._try_all_card_keys(task, 2)
                utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(len(reads), 1)

    def test_a_fresh_hand_reads_the_weakness_again(self):
        # A new turn can be a new fight, so what the last one saw no longer counts.
        with upstream(hand(ATTACK, BIG_ATTACK), weakness="PURPLE") as (utils_sortie, task):
            battle.install()
            with counting(board, "weakness") as reads:
                utils_sortie._try_all_card_keys(task, 2)
                battle.end_of_turn(task)
                task.hand_cards = hand(ATTACK, BIG_ATTACK, CURSE)
                utils_sortie._try_all_card_keys(task, 3)
            self.assertEqual(len(reads), 2)

    def test_a_hand_grown_mid_turn_keeps_the_turn_and_its_plays(self):
        with upstream(hand(ATTACK, BIG_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            turn = getattr(task, battle.TURN)
            task.hand_cards = hand(ATTACK, ATTACK, ATTACK)
            utils_sortie._try_all_card_keys(task, 3)
            self.assertIs(getattr(task, battle.TURN), turn)
            self.assertEqual(turn.played, [BIG_ATTACK])

    def test_an_end_turn_upstream_presses_closes_the_turn(self):
        # Upstream ends an empty hand itself, so the card tried last left the hand without the picker seeing it go.
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 1)
            battle.noting_end_of_turn(task)(battle.END_TURN_KEY)
            task.hand_cards = hand(ATTACK, BIG_ATTACK)
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(getattr(task, battle.TURN).last_turn, (ATTACK,))

    def test_the_next_turn_knows_what_was_kept(self):
        # The Attack was pressed after the last read, so only the Curse was still in hand when the turn ended.
        with upstream(hand(ATTACK, CURSE)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            battle.end_of_turn(task)
            task.hand_cards = hand(CURSE, ATTACK, BIG_ATTACK)
            utils_sortie._try_all_card_keys(task, 3)
            self.assertEqual(getattr(task, battle.TURN).kept, (CURSE,))

    def test_every_copy_of_a_card_gets_played(self):
        # Caught live: a hand of three Escapism played one, read the other two as the game refusing it, and
        # ended the turn with both still sitting there and still playable.
        with upstream(hand(ATTACK, ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            task.hand_cards = hand(ATTACK)
            utils_sortie._try_all_card_keys(task, 1)
            self.assertEqual(task.keys, ["1", battle.CONFIRM_KEY, "1", battle.CONFIRM_KEY])

    def test_a_card_still_in_hand_is_not_tried_again(self):
        with upstream(hand(ATTACK, BIG_ATTACK)) as (utils_sortie, task):
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            # The game kept it twice running, so the next frame should reach for the other card instead.
            utils_sortie._try_all_card_keys(task, 2)
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY, "2", battle.CONFIRM_KEY, "1", battle.CONFIRM_KEY])

    def test_a_refusal_holds_while_ocr_misreads_the_hand(self):
        # Caught live: a lowered hand read as one card spelled a new way each frame, and as one card then two,
        # while the counter held at four. Each looked like a different card or a new turn, so the same refused
        # key was pressed for over a minute.
        with upstream(hand("Homing Laser L", at=[0.541])) as (utils_sortie, task):
            task.counter = 2
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            task.hand_cards = hand(CURSE, "loming Laser L", at=[0.393, 0.541])
            utils_sortie._try_all_card_keys(task, 2)
            task.hand_cards = hand(CURSE, "oming Laser L", at=[0.393, 0.541])
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, ["2", battle.CONFIRM_KEY, "2", battle.CONFIRM_KEY, battle.END_TURN_KEY])

    def test_text_keyed_past_the_hand_size_is_not_a_card(self):
        # Live: a Bleed tooltip's lines were read as two cards and upstream counted them on to keys 5 and 9.
        read = [{"name": "Magnetic Field", "key": "1", "left_x": 0.259}, {"name": "Damage on", "key": "5", "left_x": 0.5},
                {"name": "Combatants", "key": "5", "left_x": 0.52}, {"name": "Bleed", "key": "9", "left_x": 0.675}]
        with upstream(read) as (utils_sortie, task):
            task.counter = 4
            battle.install()
            self.assertEqual([("Magnetic Field", "1"), ("Bleed", "4")],
                             [(card["name"], card["key"]) for card in utils_sortie._hand_cards(task)])

    def test_a_hand_read_short_is_keyed_by_where_each_card_sits(self):
        # The same lowered hand: only the raised fourth card was read, and upstream keyed it 1 - Pulse Fire, which
        # cost the point the turn no longer had. Measured off the capture, Homing Laser L's name starts at 0.705.
        with upstream(hand("Homing Laser L", at=[0.705])) as (utils_sortie, task):
            task.counter = 4
            task.all_texts = [FakeBox("Not enough AP.", 0.5, 0.52)]
            battle.install()
            utils_sortie._try_all_card_keys(task, 4)
            self.assertEqual(task.keys, ["4", battle.CONFIRM_KEY])

    def test_a_card_ocr_missed_is_tried_before_the_turn_ends(self):
        # Live: the counter read three, OCR read only two status cards at keys 2 and 3, and the turn was ended
        # with Cobalt Light, the unread first card, still in hand and points to spend.
        with upstream(hand(CURSE, CURSE, at=[0.468, 0.605])) as (utils_sortie, task):
            task.counter = 3
            battle.install()
            utils_sortie._try_all_card_keys(task, 3)
            utils_sortie._try_all_card_keys(task, 3)
            self.assertEqual(task.keys, ["1", battle.CONFIRM_KEY, battle.END_TURN_KEY])

    def test_the_games_out_of_points_toast_ends_the_turn(self):
        # The readout read as lit behind the lowered hand, so only the toast said the turn was spent.
        with upstream(hand(ATTACK, BIG_ATTACK), action_points=True) as (utils_sortie, task):
            task.all_texts = [FakeBox("Not enough AP.", 0.5, 0.52)]
            battle.install()
            utils_sortie._try_all_card_keys(task, 2)
            self.assertEqual(task.keys, [battle.END_TURN_KEY])


class TestCallingBackTheTurn(unittest.TestCase):
    """A hand the game has not raised yet reads as empty, and upstream ends the turn on an empty read."""

    def run_frames(self, *, names, popups):
        """Run one battle frame, then the popup handler on each popup frame after it.

        Args:
            names: The card names the hand read returns on the battle frame.
            popups: How many frames the game's "cards can still be used" check stays up for.

        Returns:
            The task, and what the popup handler returned on each popup frame.
        """
        with upstream([]) as (utils_sortie, task):
            task.counter = 7
            utils_sortie._hand_card_names = lambda _: list(names)
            battle.install()
            handlers = handlers_of(utils_sortie)
            handlers["handle_battle_page"](task)
            answers = []
            for _ in range(popups):
                task.all_texts = list(CARDS_LEFT_PROMPT)
                answers.append(handlers["handle_cards_left"](task))
        return task, answers

    def test_ending_on_an_unread_hand_is_called_back(self):
        task, answers = self.run_frames(names=[], popups=1)
        self.assertEqual(answers, [True])
        self.assertEqual([box.name for box in task.clicked], ["取消"])

    def test_an_end_the_picker_chose_is_left_to_confirm(self):
        task, answers = self.run_frames(names=[ATTACK], popups=1)
        self.assertEqual(answers, [False])
        self.assertEqual(task.clicked, [])

    def test_a_hand_that_never_reads_is_not_called_back_forever(self):
        task, answers = self.run_frames(names=[], popups=battle.CALLBACKS + 1)
        self.assertEqual(answers, [True] * battle.CALLBACKS + [False])

    def test_a_card_passed_over_for_cost_is_tried_once_the_game_says_it_plays(self):
        # Live, Rossweisse's Sword Resonance showed 0 AP against the data's 1, and was held at 0 AP for good.
        with upstream(hand("Sword Resonance"), action_points=False) as (utils_sortie, task):
            battle.install()
            handlers = handlers_of(utils_sortie)
            utils_sortie._try_all_card_keys(task, 1)
            task.all_texts = list(CARDS_LEFT_PROMPT)
            self.assertTrue(handlers["handle_cards_left"](task))
            task.all_texts = []
            utils_sortie._try_all_card_keys(task, 1)
            self.assertEqual(task.keys, [battle.END_TURN_KEY, "1", battle.CONFIRM_KEY])
            # Asked once a turn, so a card the game will not take after all cannot hold the turn open.
            task.all_texts = list(CARDS_LEFT_PROMPT)
            self.assertFalse(handlers["handle_cards_left"](task))

    def test_a_hand_still_unread_after_a_callback_has_its_keys_tried(self):
        # Live, a 0 AP card never read over its holographic art, so each callback came back to the same empty hand.
        with upstream([]) as (utils_sortie, task):
            task.counter = 3
            battle.install()
            handlers = handlers_of(utils_sortie)
            page, cards_left = handlers["handle_battle_page"], handlers["handle_cards_left"]
            page(task)
            task.all_texts = list(CARDS_LEFT_PROMPT)
            self.assertTrue(cards_left(task))
            # Key 2 plays and a card is drawn after it. Live, the draw started the keys over from 1, retrying cards the game had
            # already refused, while the card right of the one played slid onto its key. A key the game turns down at once
            # is not confirmed, which saves the 2s wait on Enter.
            toast = [FakeBox("Not enough AP.", 0.5, 0.52)]
            for counter, texts in ((3, []), (3, toast), (3, []), (2, []), (2, []), (3, []), (3, toast)):
                task.counter = counter
                task.all_texts = list(texts)
                page(task)
            self.assertEqual(task.keys, ["1", "2", battle.CONFIRM_KEY, "2", battle.CONFIRM_KEY, "3"])
            # Every key tried, so the game's next check is the end of the turn.
            task.all_texts = list(CARDS_LEFT_PROMPT)
            self.assertFalse(cards_left(task))


class TestEgoChoice(unittest.TestCase):
    """Which Ego skill gets fired. Upstream picks one of the three at random, affordable or not."""

    def fire(self, utils_sortie, task):
        """Run one battle frame and report what it fired, as the frame itself saw it.

        Args:
            utils_sortie: The fake upstream module.
            task: The task the frame runs against.

        Returns:
            What upstream's own `random.choice(["F1", "F2", "F3"])` returned during the frame.
        """
        utils_sortie.PAGE_HANDLERS[0](task)
        return utils_sortie.asked[-1]["ego"]

    def test_an_affordable_ego_is_chosen(self):
        with upstream(hand(ATTACK), egos=("F2",)) as (utils_sortie, task):
            battle.install()
            self.assertEqual(self.fire(utils_sortie, task), "F2")

    def test_only_the_affordable_ones_are_chosen_between(self):
        # Firing one the bar cannot pay for is the defect. Which of the affordable ones goes is still left to
        # chance, so a fight fought twice does not open the same way both times.
        with upstream(hand(ATTACK), egos=("F2", "F3")) as (utils_sortie, task):
            battle.install()
            self.fire(utils_sortie, task)
            self.assertEqual(utils_sortie.offered[0], ["F2", "F3"])

    def test_nothing_affordable_falls_back_to_upstream(self):
        # Upstream fires only when it believes the bar is full, so if no badge reads as affordable the
        # reading is more likely wrong than the game is, and guessing beats refusing to act.
        with upstream(hand(ATTACK), egos=()) as (utils_sortie, task):
            battle.install()
            self.fire(utils_sortie, task)
            self.assertEqual(utils_sortie.offered[0], list(board.EGO_KEYS))

    def test_every_other_random_choice_is_left_alone(self):
        with upstream(hand(ATTACK), egos=("F1",)) as (utils_sortie, task):
            battle.install()
            utils_sortie.PAGE_HANDLERS[0](task)
            self.assertEqual(utils_sortie.asked[-1]["other"], "a")
            self.assertEqual(utils_sortie.asked[-1]["wait"], 0.2)


class TestStartingTheFight(unittest.TestCase):
    """A fight entered from a Sortie event opens on an Attack button, and upstream's Sortie frame waited on it forever."""

    def test_the_attack_button_is_pressed_before_upstream_waits(self):
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            task.attack_button = types.SimpleNamespace(confidence=0.99)
            battle.install()
            self.assertTrue(utils_sortie.PAGE_HANDLERS[0](task))
            self.assertEqual(task.clicked, [task.attack_button])
            self.assertEqual(utils_sortie.asked, [])

    def test_upstreams_template_matches_the_global_button(self):
        # The template was cut from the Chinese client. `attack_button.png` is `START_ATTACK_REGION` cut out of
        # a Global frame, and the framework's default cutoff is 0.8.
        annotations = json.loads((REPO_ROOT / "ok_tasks" / "assets" / "coco_annotations.json").read_text(encoding="utf-8"))
        category = next(c["id"] for c in annotations["categories"] if c["name"] == battle.START_ATTACK)
        found = next(a for a in annotations["annotations"] if a["category_id"] == category)
        image = next(i["file_name"] for i in annotations["images"] if i["id"] == found["image_id"])
        x, y, width, height = found["bbox"]
        template = cv2.imread(str(REPO_ROOT / "ok_tasks" / "assets" / image))[y:y + height, x:x + width]
        region = cv2.imread(str(REPO_ROOT / "tests" / "images" / "attack_button.png"))
        score = cv2.minMaxLoc(cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))[1]
        self.assertGreaterEqual(score, 0.8)


class TestKits(unittest.TestCase):
    """Rossweisse's Shards, which need the turn and its prompts handled differently, not just the cards ranked differently."""

    # Her hand mid-turn, as a hand prompt reads it.
    SHARDS_AROUND_A_SLASH = (("Shard:Light", 0.25), ("Sword Slash", 0.50), ("Shard:Dark", 0.75))

    def test_the_turn_waits_for_the_shards_to_fuse(self):
        # Upstream ends the turn on an empty read, and the hand reads empty for a second mid-fusion.
        with upstream(hand("Shard:Light", "Sword Slash", "Shard:Dark")) as (utils_sortie, task):
            battle.install()
            page = handlers_of(utils_sortie)["handle_battle_page"]
            utils_sortie._try_all_card_keys(task, 3)
            # The Tassels the Shards made sit in hand with them until they fuse.
            task.hand_cards = hand("Shard:Light", "Sword Tassel", "Shard:Dark")
            # A counter that blanks mid-animation is no reason to wait, and no reason to raise either.
            self.assertFalse(battle.kit_waiting(task, utils_sortie, None))
            page(task)
            task.hand_cards, task.counter = [], 2
            for _ in range(battle.KIT_WAIT - 1):
                page(task)
            self.assertEqual(utils_sortie.asked, [])
            # A fusion that never comes cannot hold the turn for good.
            page(task)
            self.assertEqual(len(utils_sortie.asked), 1)

    def test_a_hand_prompt_never_gives_up_a_shard(self):
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            task.all_texts = [FakeBox(name, x, 0.80) for name, x in self.SHARDS_AROUND_A_SLASH]
            handlers_of(utils_sortie)["handle_battle_hand_select"](task)
            self.assertEqual([box.name for box in task.clicked], ["Sword Slash"])

    def test_return_to_draw_pile_passes_over_the_shard_on_the_left(self):
        # Upstream's own handler takes the leftmost card, and the leftmost card is always Shard:Light.
        for description, in_hand, expected in (
                ("a card between the Shards", self.SHARDS_AROUND_A_SLASH, "Sword Slash"),
                # Card text in the same band is not a card, so it must not count as one still to clear.
                ("only the Shards, over their card text", (("Shard:Light", 0.25), ("150% Damage", 0.50), ("Shard:Dark", 0.75)), "Shard:Light"),
        ):
            with self.subTest(description):
                task = Pressed([])
                task.all_texts = [FakeBox("请选择1张要移动至抽牌堆的卡牌", 0.484, 0.111, width=600), *(FakeBox(name, x, 0.80) for name, x in in_hand)]
                with standing_in(task, all_texts=battle.unheld_texts(task)):
                    self.assertTrue(real_sortie.handle_return_to_draw_pile(task))
                self.assertEqual([box.name for box in task.clicked], [expected])


class TestHandPrompt(unittest.TestCase):
    """The prompt that takes cards out of the hand mid-fight, answered against its own counter."""

    # Precision Aim's prompt as it stuck live: upstream tapped "Basi", "Fixer's Approach" and "XAttac" while the counter stayed at 0/1.
    SCREEN = (FakeBox("请选择1张要移动至抽牌堆的卡牌", 0.5, 0.111, width=600), FakeBox("05/10", 0.505, 0.971), FakeBox("Launcher", 0.273, 0.721),
              FakeBox("Basi", 0.27, 0.80), FakeBox("Opening Found", 0.349, 0.765), FakeBox("Hunting Instincts", 0.603, 0.757), FakeBox(CURSE, 0.73, 0.776))

    def frames(self, *counters, screens=(), played=None):
        """Answer the prompt once per counter reading.

        Args:
            counters: What a cropped read of the prompt's counter gives each frame, empty for nothing read.
            screens: What the full-screen pass reads on the first frames, `SCREEN` for every frame after them.
            played: The card whose key opened the prompt, or None for a turn not tracked.

        Returns:
            The task, with every tap it made.
        """
        with upstream(hand(ATTACK)) as (utils_sortie, task):
            battle.install()
            if played:
                turn = battle.Turn(5)
                turn.attempted = played
                setattr(task, battle.TURN, turn)
            for index, counter in enumerate(counters):
                task.all_texts = list(screens[index] if index < len(screens) else self.SCREEN)
                task.progress = [FakeBox(counter, 0.5, 0.17)] if counter else []
                handlers_of(utils_sortie)["handle_battle_hand_select"](task)
        return task

    def test_it_gives_up_the_curse_and_confirms_only_once_the_counter_moves(self):
        task = self.frames("0/1", "1/1")
        self.assertEqual([(0.73, round(0.776 + battle.CARD_BODY, 3)), battle.PROMPT_CONFIRM], task.taps)
        self.assertEqual([], task.clicked, "upstream's random pick never ran")

    def test_the_top_of_the_draw_pile_takes_the_dearest_card_then_the_best_over_the_curse(self):
        # The card comes straight back next turn, so a curse put there is drawn again.
        top = (FakeBox("请选择1张要移动至抽牌堆顶的卡牌", 0.5, 0.111, width=600), *self.SCREEN[1:])
        task = self.frames("0/1", screens=(top,))
        self.assertEqual([(0.349, round(0.765 + battle.CARD_BODY, 3))], task.taps, "Opening Found, the best of the 1-cost cards")
        task = self.frames("0/1", screens=((*top, FakeBox("Android", 0.45, 0.765)),))
        self.assertEqual([(0.45, round(0.765 + battle.CARD_BODY, 3))], task.taps, "Android, the one 2-cost card, though Opening Found rates higher")

    def test_a_boost_goes_to_the_best_card_it_fits(self):
        # Opening Found rates highest, but Growth Acceleration can only pick Orlea's own cards, and the curse is no boost at all.
        cases = (("Growth Acceleration", (*self.SCREEN, FakeBox("Growing Creature", 0.45, 0.765)), 0.45),
                 ("Dark Condensation", self.SCREEN, 0.349))
        for played, screen, x in cases:
            with self.subTest(played=played):
                task = self.frames("0/1", screens=(screen,), played=played)
                self.assertEqual([(x, round(0.765 + battle.CARD_BODY, 3))], task.taps)

    def test_a_hand_not_read_yet_is_waited_for(self):
        # Live, the prompt opened on a frame with no card name read, and upstream's random pick gave up an Impulse over the curse.
        task = self.frames("0/1", "0/1", screens=(self.SCREEN[:2],))
        self.assertEqual([(0.73, round(0.776 + battle.CARD_BODY, 3))], task.taps)
        self.assertEqual([], task.clicked, "upstream's random pick never ran")

    def test_upstream_takes_over_from_a_counter_that_never_moves_or_never_reads(self):
        # A prompt that ignores every tap must not hold the fight for good.
        for counters, taps in ((("0/1",) * (battle.PROMPT_TAPS + 1), battle.PROMPT_TAPS), (("",), 0)):
            with self.subTest(counters=counters):
                task = self.frames(*counters)
                self.assertEqual(taps, len(task.taps))
                self.assertEqual(1, len(task.clicked))


if __name__ == "__main__":
    unittest.main()
