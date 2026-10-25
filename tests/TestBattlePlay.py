"""Check what the picker does with a hand once a turn is under way.

`cards.py` decides what a hand is worth. This is the layer above it: which card actually gets a key pressed
for it, what happens when the game refuses one, and when a turn should just be ended.
"""

import json
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import battle, board, cards, overrides  # noqa: E402
from tests.TestBoard import FakeTask, flat, paint, paint_enemy, pasted  # noqa: E402
from tests.fakes import FakeBox  # noqa: E402

# Haru is Justice and Renoa is Void, and these two cards are otherwise identical: one Action Point, an
# Attack, exactly "100% Damage". So only a weakness read off the screen can order them.
ATTACK = "Anchor"
VOID_ATTACK = "Annihilation Shot"
BIG_ATTACK = "Charge Launcher"
CURSE = "Anemia"

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
        # ahead of Parasitic Spores, while Abyssal Erosion does its harm when played and is left alone.
        for held, cleared in ((("Parasitic Spores", "Bleed"), "Bleed"), (("Abyssal Erosion",), None)):
            with self.subTest(held=held):
                chosen = battle.choose(hand(*held), cards.Board(), set())
                self.assertEqual(cleared, chosen and chosen["name"])

    def test_an_empty_hand_ends_the_turn(self):
        self.assertIsNone(battle.choose([], cards.Board(), set()))


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

    def test_a_bigger_hand_means_a_new_turn(self):
        self.assertTrue(battle.new_turn(before=1, after=5))

    def test_the_same_hand_is_not_a_new_turn(self):
        self.assertFalse(battle.new_turn(before=5, after=5))

    def test_a_shrinking_hand_is_not_a_new_turn(self):
        self.assertFalse(battle.new_turn(before=5, after=4))

    def test_the_first_frame_of_a_battle_is_a_new_turn(self):
        self.assertTrue(battle.new_turn(before=None, after=5))


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

    def send_key(self, key):
        self.keys.append(key)

    def box_of_screen(self, *region):
        return region

    def find_one(self, feature_name=None, box=None):
        return self.attack_button if feature_name == battle.START_ATTACK else None

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
    # The seam edits this list rather than the module attribute, so the fake has to carry one too, with the anchor
    # the fork inserts its own handler in front of.
    utils_sortie.PAGE_HANDLERS = [handle_battle_page, types.SimpleNamespace(__name__="handle_center_confirm")]
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
            gate, picker, *_ = utils_story.PAGE_HANDLERS
            self.assertEqual([gate, picker, battle.handle_cards_left, confirm], utils_story.PAGE_HANDLERS)
            self.assertIsNot(picker, utils_sortie.handle_battle_page)
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
                task.hand_cards = hand(ATTACK, BIG_ATTACK, CURSE)
                utils_sortie._try_all_card_keys(task, 3)
            self.assertEqual(len(reads), 2)

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

if __name__ == "__main__":
    unittest.main()
