"""Play a Sortie battle from what the cards do, instead of pressing every hotkey and hoping.

Upstream's `handle_battle_page` plays the first hand card matching the user's Play Priority list. That list
starts empty on the Global client, so every turn falls through to `_try_all_card_keys`, which presses each
hotkey from the hand size down at about a second and a half a press - thirteen seconds of blind input at nine
cards, playing whatever sat under the last key that worked. That fallback is the only thing replaced. Upstream
keeps the frame around it, and a card the Play Priority list names is still played by upstream unchanged.
"""

import collections
import math
import re

import cv2
import numpy as np
from ok import Logger

from src.en import board, cards, ego, kits
from src.en.handlers import StandIn, insert_before, loaded, register, replace, standing_in
from src.en.overrides import SMART_CARD_PLAY
from src.en.screen import centre_of, colour_share, frame_of, in_region, patch_of, text_in_region

logger = Logger.get_logger(__name__)

# Parked on the task for the length of a battle, the way upstream parks `_play_stuck_count` and
# `_last_attempted_card`. One attribute, so starting a fresh turn is one assignment rather than three that
# have to agree. The prefix keeps it clear of anything upstream owns.
TURN = "_en_turn"
# Remembers one frame's hand reading, keyed on the OCR pass it came from. `SortieMode.run` builds a fresh
# `all_texts` list every frame, so identity tells frames apart, and a matching list can only ever produce a
# matching hand. Upstream reads the hand twice a frame already; this makes all of those one reading.
HAND_CACHE = "_en_hand_for"
# The combatants in the party, parked on the task. Read off the Combatants screen at the start of a run, then topped up from the
# owners of cards read in hand.
PARTY = "_en_party"
# Set by Sortie's team read when a turn had a card or end turn in flight, so the next turn opens with a frame spare for the tap.
TEAM_WANTED = "_en_team_wanted"

# Upstream's own timings for playing a card, kept so the two paths feel the same to the game.
AFTER_KEY = 1
AFTER_CONFIRM = 2
# The key that ends a turn, as upstream sends it.
END_TURN_KEY = "e"
CONFIRM_KEY = "enter"
# Upstream's template for the Attack button a fight entered from an event opens on, and the box Chaos looks for it in.
# It scores 0.997 on the Global client's button and at most 0.41 on the 711 other captures.
START_ATTACK = "start_attack_event"
START_ATTACK_REGION = (0.394, 0.779, 0.600, 0.858)
# The toast the game puts up when a card costs more than is left. It is the one sure reading of an empty turn: a
# lowered hand spills card art over the readout `board.has_action_points` judges, which then reads as lit.
NO_POINTS = "Not enough AP"
# Where that toast sits, across the middle of the screen. Measured at (0.502, 0.501).
NO_POINTS_REGION = (0.30, 0.42, 0.70, 0.58)
# The Action Point digit, a little wider than `board.ACTION_POINTS`. OCR finds it only once the crop is enlarged and padded with black,
# and then reads every count but most 1s and digits under a skill's flash: 51 of 76 lit frames, from 1 to 6, all of them right.
POINTS_DIGIT = (0.478, 0.888, 0.538, 0.958)
POINTS_ZOOMS = (3, 2)
POINTS_MARGIN = 20
POINTS_SURE = 0.9
# The game's own check when a turn is ended with a card it would still play, so it is the one reading that knows the
# Action Points: it followed 2 of 18 empty-read turn ends in the logs, exactly the 2 that had cards left to play.
CARDS_LEFT = "can still be used"
CARDS_LEFT_REGION = (0.15, 0.20, 0.85, 0.60)
# The check's Cancel button, which the catalog reads back as Chinese.
CANCEL = "取消"
CANCEL_REGION = (0.15, 0.45, 0.55, 0.80)
# The title of the pick between created cards that an Ego such as Archetype Resonance raises. Upstream has no handler for it, so it sat 11s
# for the stuck-screen fallback's random click. Its title reads above the cards' names, which sit at y ~0.29.
ATTRIBUTE_CHOICE = "Select an attribute"
ATTRIBUTE_CHOICE_REGION = (0.20, 0.00, 0.80, 0.26)
# Parked on the task while the hand reads empty under a counter that says it is not: how many times the end of the turn
# has been called back since, or None once the hand reads again.
UNREAD_HAND = "_en_unread_hand"
# Callbacks before the game's check is taken as final, so a hand that never reads cannot stall the turn for good. Each
# one takes about 3s, and a hand has stayed lowered for up to 12s after a play.
CALLBACKS = 4
# Parked on the task while keys are pressed blind into an unread hand, as a `Blind`. Kept off `Turn`, which a card drawn
# mid-turn starts afresh.
BLIND = "_en_blind"
# Where the hand lays out its cards, by hand size: the left edge of the first and of the last card's name. Medians
# over ~2,600 fully read hands in the September logs, one sighting at 8. Wider hands are taken to span as 7 does.
HAND_SPAN = {2: (0.393, 0.541), 3: (0.328, 0.605), 4: (0.259, 0.675), 5: (0.240, 0.696),
             6: (0.233, 0.711), 7: (0.220, 0.721)}
WIDEST_SPAN = (0.218, 0.730)
# Only keys 1-9 exist, so a tenth card has no key to press.
MAX_KEY = 9
# How many times a card has to stay in hand after its key is pressed before it is left for the rest of the turn.
REFUSALS = 2
# Sortie's battle screens in its own order: the prompts a card can raise mid-fight, then the fight itself. Story mode
# borrows them for the fights where the game's Auto is locked, since its own handler only turns Auto on and waits.
BATTLE_SCREENS = ("handle_battle_crash", "handle_discard_hand_card", "handle_battle_hand_select", "handle_curiosity_activate",
                  "handle_extra_card_use", "handle_card_function_select", "handle_return_to_draw_pile", "handle_weakness_info",
                  "handle_battle_page")
# Story's Auto handler, which the borrowed screens sit behind. Matched as a prefix, because the recorder renames it.
AUTO_CHECK = "handle_battle_auto_check"
# The Auto button, and the flat grey of the padlock it shows where a fight does not allow Auto. The padlock covers 0.096-0.100
# of the box on three locked fights, and Auto lit gold or any other screen covers at most 0.027.
AUTO_BUTTON = (0.855, 0.020, 0.900, 0.085)
LOCK_LOW = np.array((0, 0, 120), dtype=np.uint8)
LOCK_HIGH = np.array((180, 30, 215), dtype=np.uint8)
MIN_LOCK = 0.05
# A button this bright is drawn plainly: the padlock peaks at 170, and Auto lit gold or white at 255. A prompt's shade drops the
# padlock to 74, too dim to tell from the gold, so a shaded button keeps the answer its last plain reading gave. With no plain
# reading yet, the prompt screens get to look, since Auto's own check would only wait on a prompt.
PLAIN_BUTTON = 120
# Parked on the task, so a prompt in a locked fight is still known to be one.
AUTO_LOCKED = "_en_auto_locked"
# Frames a turn may sit waiting on a kit before playing on regardless, and the pause each one takes. Rossweisse's Shards read
# alone for 1-2s before they fuse, so five half-second frames cover it however fast the loop runs.
KIT_WAIT = 5
KIT_PAUSE = 0.5
# Frames a read that lost cards the last one held is waited on, a hand size at a time. Live, a Rhythm's hit still played over the hand
# 2s after its key, and the read caught 1 of 6 cards.
SETTLE_WAIT = 2
# Where upstream's hand prompts read the hand cards they choose between.
PROMPT_HAND = (0.116, 0.697, 0.859, 0.908)
# The hand prompt as upstream finds it: its caption, rewritten to Chinese by `ocr_text.py`, over a hand counter reading "5/10".
PROMPT_CAPTION = (0.5, 0.111)
PROMPT_ASKS = re.compile(r"请选择(?=.*卡牌).*?\d+张")
# The word `ocr_text.py` keeps for the top of the Draw Pile, where the card picked comes straight back next turn.
PROMPT_TOP = "抽牌堆顶"
HAND_COUNTER = (0.505, 0.971)
HAND_TOTAL = re.compile(r"\d+/10")
# The prompt's own "0/1" under its caption. The full-screen pass never reads it, and a crop of it read 1/1 at 0.99 on both captures.
PROMPT_PROGRESS = (0.40, 0.14, 0.60, 0.20)
PROGRESS = re.compile(r"(\d+)\s*/\s*(\d+)")
# Card text whose prompt picks a hand card to boost rather than give up, as Growth Acceleration, Dark Condensation and Sir Kowalski do.
# `kind` narrows the pick to Attack cards or cards so named, and `own` to the played card's combatant. An Epiphany of Dark Condensation
# reads "Choose 1 Attack Card(s) in hand, +X% Damage Amount", with the boost straight after the comma.
BOOST = re.compile(r"(?:select|choose) (?:up to )?\d+ (?P<kind>[a-z ]*?) ?cards?(?:\(s\))?(?P<own> of this unit)? in hand,? (?:(?:then|and) (?!move)|(?=\+))",
                   re.I)
# How a card's text marks the line its Retain effect runs, which a boost that activates Retain needs to be worth anything.
RETAIN_LINE = "Retain:"
# How far below a card's name to tap it, onto its art. Upstream tapped a type label's fragment and the prompt stayed at 0/1.
CARD_BODY = 0.07
# Frames a prompt gets without its counter moving before upstream's random pick takes over. A frame with no card read counts,
# since the prompt can open before the hand's names do.
PROMPT_TAPS = 3
PROMPT_CONFIRM = (0.934, 0.883)
# Parked on the task while a hand prompt is being answered, as a `Prompt`.
PROMPT = "_en_prompt"

_patched = False


Blind = collections.namedtuple("Blind", [
    # The hand size the counter read when the last key was pressed.
    "count",
    # The last key pressed, or None before the first.
    "key",
    # Keys known to hold a card the game would not take, as a frozenset of key strings.
    "refused",
    # Whether Enter has followed the last key. Held back a frame, since the game refuses a card at its key.
    "confirmed",
])


class Prompt:
    """What answering one hand prompt has done so far, kept between frames."""

    def __init__(self):
        # How many cards the prompt's counter read as chosen last frame.
        self.chosen = 0
        # Frames spent since that count last moved, tapping or waiting for the hand to read.
        self.taps = 0
        # Canonical names of the cards the counter has confirmed taken, so a prompt asking for two does not tap the first again.
        self.picked = []
        # The card tapped last, which joins `picked` once the counter moves.
        self.tapped = None


class EgoChoice(StandIn):
    """Stands in for the module's `random` while one battle frame runs.

    Only the Ego question is answered here. Every other call - and there are several in that module, for
    picking a card to drag at a Secret Enemy and for the hand-select screens - is handed to the real `random`
    untouched, which is what `StandIn` is for.
    """

    def __init__(self, task, original):
        """Stand in for one frame.

        Args:
            task: The task the frame is running against, whose screen holds the answer.
            original: The module's real `random`, which everything else still goes to.
        """
        super().__init__(original)
        self.task = task

    def choice(self, options):
        """Answer a random choice, narrowing the Ego question to what the EP bar can pay for.

        The defect being fixed is that upstream picks an Ego it cannot afford, not that it picks at random.
        So the choice stays random and only the shortlist changes, which keeps a repeated fight from always
        firing the same Ego.

        Args:
            options: What upstream is choosing between.

        Returns:
            One of the affordable Ego keys when that is the question being asked and the screen gives an
            answer, otherwise whatever the real `random` says.
        """
        if list(options) == list(board.EGO_KEYS):
            ready = board.affordable_egos(self.task)
            if ready:
                firing = self.original.choice(ready)
                logger.info(f"the EP bar covers {', '.join(ready)}, firing {firing}")
                return firing
            # Upstream reads the bar as full and fires anyway, so this is the case worth naming.
            logger.info("the EP bar covers no Ego, so upstream's pick would not have played")
        return self.original.choice(options)


def kept_boxes(boxes):
    """Find the hand cards a kit is keeping among some OCR boxes, judged against the boxes that read as cards.

    Args:
        boxes: OCR boxes off the hand, which may hold cost digits and card text as well as names.

    Returns:
        The `id` of every box a kit is keeping.
    """
    named = []
    for box in boxes:
        name = cards.canonical(getattr(box, "name", ""))
        if name in cards.CARD_COST or kits.active([name]):
            named.append((box, name))
    names = [name for _, name in named]
    hand = cards.Board(hand=tuple(names))
    return {id(box) for box, name in named if kits.held(name, hand)}


class KeepHeld(StandIn):
    """Stands in for the module's `random` while a hand prompt runs, so it never gives up a card a kit is keeping."""

    def choice(self, options):
        """Choose at random among the hand cards on offer, leaving out the ones a kit is keeping.

        Args:
            options: What upstream is choosing between, the OCR boxes of the hand cards for a hand prompt.

        Returns:
            One of the options no kit is keeping, or one of all of them when a kit would keep every one.
        """
        options = list(options)
        kept = kept_boxes(options)
        if kept:
            logger.info(f"leaving {[option.name for option in options if id(option) in kept]} out of the hand prompt")
        return self.original.choice([option for option in options if id(option) not in kept] or options)


def choose(hand, board, refused):
    """Pick the card to play next, or nothing when the turn is done.

    A turn is planned against the points the readout shows, or a full three when it does not read. The game refuses
    a card there is no room for, so a wrong guess corrects itself against the game.

    Args:
        hand: Hand cards as `_hand_cards` reads them.
        board: The `cards.Board` to decide against.
        refused: Names the game has already declined to play this turn.

    Returns:
        The hand card to play, or None when nothing is left worth playing.
    """
    playable = [card for card in hand if card.get("key") and card["name"] not in refused]
    chosen = cards.plan(playable, board)
    if chosen:
        return chosen[0]
    # Nothing is worth playing for its own sake, so what is left goes on getting rid of cards that hurt while held.
    # Live, three Bleeds sat out turn after turn with all three points unspent.
    clearing = [card for card in playable
                if cards.worth_clearing(card["name"]) and cards.price(card) <= board.action_points]
    return min(clearing, key=lambda card: cards.clearing_order(card["name"]), default=None)


def was_refused(attempted, copies, hand_names):
    """Say whether the card tried last frame is still sitting in hand.

    How many copies are left is what settles it: one fewer than there were means the game took it. Neither the
    size of the hand nor the presence of the card answers it, since a card that draws replaces itself and a
    deck holds several copies of one name.

    Args:
        attempted: The card name tried last frame, or None when nothing was.
        copies: How many of that card were in hand when its key was pressed.
        hand_names: The names now in hand.

    Returns:
        True when the game would not play it, so it should be passed over for the rest of the turn.
    """
    return attempted is not None and hand_names.count(attempted) >= copies


def new_turn(before, after, ended):
    """Say whether the hand has been dealt again since the last frame.

    A hand also grows mid-turn, when a card draws or creates cards - Luke's Stealth Reload adds bullets - so a bigger
    hand only means a new deal once the turn has been ended.

    Args:
        before: The hand size last frame, or None on the first frame of a battle.
        after: The hand size now.
        ended: Whether end turn has been pressed since the turn began.

    Returns:
        True when a fresh turn has started, so what the last turn refused no longer applies.
    """
    return before is None or (ended and after > before)


def fight_of(task):
    """Say which fight the battle screen belongs to, from the map node upstream counts on leaving the route screen.

    Args:
        task: The running task, whose `node_status` Sortie and Chaos keep.

    Returns:
        The run, floor and node the fight is on, or None in a mode that counts no nodes.
    """
    status = getattr(task, "node_status", None)
    if status is None:
        return None
    return getattr(task, "start_time", None), status.get("pass_final_boss_count"), status.get("node_count")


def unsettled(turn, names, count):
    """Find the cards a short read lost since the last one, counting the frame it is about to wait.

    Args:
        turn: The `Turn` in progress, holding the hand last read and the card pressed since.
        names: The canonical names read this frame.
        count: The hand size the counter read.

    Returns:
        The cards missing besides the one pressed, empty when the read is whole or this hand size has been waited on enough.
    """
    expected = collections.Counter(turn.hand)
    if turn.attempted:
        expected[turn.attempted] -= 1
    lost = expected - collections.Counter(names)
    size, waits = turn.settling
    waits = waits if size == count else 0
    if not count or len(names) >= count or not lost or waits >= SETTLE_WAIT:
        return []
    turn.settling = (count, waits + 1)
    return sorted(lost.elements())


class Turn:
    """What one turn has learnt: the hand it last saw, the card it tried, and what the game would not play.

    The weakness the enemies show belongs here rather than to the frame. It is a property of the fight, it
    costs a pass over a third of the screen to read, and an attack landing over an enemy hides its badge for
    a frame or two - so it is read once and kept, and a turn that never manages to read one keeps trying.
    """

    def __init__(self, hand_count, last_turn=(), kept=(), earlier=(), fight=None):
        """Start a turn that has learnt nothing yet.

        Args:
            hand_count: The hand size this turn opened with.
            last_turn: The cards the turn before played, oldest first.
            kept: The cards the turn before ended holding.
            earlier: The cards the turns before played this battle, oldest first.
            fight: The fight it belongs to, from `fight_of`.
        """
        self.hand_count = hand_count
        self.fight = fight
        self.earlier = tuple(earlier)
        self.attempted = None
        self.attempted_copies = 0
        self.refused = set()
        # How many frames each card has stayed in hand after its key was pressed, since one can be a frame too soon.
        self.misses = collections.Counter()
        # Keys pressed for a card the counter says is there but OCR never read, each tried once a turn.
        self.blind = set()
        # Cards passed over for costing more than was left, held when the turn was ended for want of points. A cost can
        # drop mid-fight - Rossweisse's Sword Resonance showed 0 against the data's 1 - so the game may still take one.
        self.priced_out = []
        # Whether the game has already said a card can still be played after the picker ended the turn this turn.
        self.objected = False
        self.weakness = None
        # Frames spent waiting on a kit this turn, and whether the last frame was one.
        self.kit_waits = 0
        self.kit_waited = False
        # The hand size last waited on for a read that lost cards, and how many frames it has waited.
        self.settling = (None, 0)
        # Cards the game took this turn, oldest first, and those the turn before took, for kits that count plays.
        self.played = []
        self.last_turn = tuple(last_turn)
        # The hand last read this turn, less a card pressed after it, and the one the turn before ended with.
        self.hand = []
        self.kept = tuple(kept)
        # Whether end turn has been pressed, by the picker or by upstream, and not called back since.
        self.ended = False
        # Egos fired this turn, whether a press has already failed to take, and whether holding EP has been logged.
        self.ego_fires = 0
        self.ego_missed = False
        self.ego_held = False
        # Whether an enemy shows Absolute Invincibility, from `watch_invulnerable`, so the picker holds its attacks.
        self.invulnerable = False
        # The fewest enemies a frame of this turn has shown, from `board.enemy_counters`. 0 until a frame shows one.
        self.enemies = 0


def play_key(task, key):
    """Play the card on a key, with upstream's own timings so both paths feel the same to the game.

    Args:
        task: The running task.
        key: The hotkey of the card to play.
    """
    task.send_key(key)
    task.sleep(AFTER_KEY)
    confirm(task)


def confirm(task):
    """Press Enter on the card a key raised, and wait as upstream does for it to resolve.

    Args:
        task: The running task.
    """
    task.send_key(CONFIRM_KEY)
    task.sleep(AFTER_CONFIRM)


def unread_key(hand, count, tried):
    """Find a key the hand counter says holds a card that OCR did not read, and that has not been tried yet.

    Args:
        hand: The hand cards read this frame, keyed by position when the read came up short.
        count: The hand size the hand counter reads.
        tried: Keys already pressed blind this turn.

    Returns:
        The key as a string, or None when every card is accounted for.
    """
    read = {card.get("key") for card in hand}
    return next((str(key) for key in range(1, min(count, MAX_KEY) + 1) if str(key) not in read | tried), None)


def start_attack(task, utils_sortie):
    """Press the Attack button a fight entered from an event opens on.

    Chaos presses it from its own battle handler, but Sortie's never looks. The button hides the end-turn
    button, so upstream's Sortie frame waits for that forever.

    Args:
        task: The running task, whose current frame is searched.
        utils_sortie: Upstream's Sortie module, whose hand count says this is a battle screen at all.

    Returns:
        True when the button was on screen and has been pressed.
    """
    # The hand count is up behind the button, so as in Chaos it keeps the search off every other screen.
    if utils_sortie._read_hand_count(task) is None:
        return False
    button = task.find_one(feature_name=START_ATTACK, box=task.box_of_screen(*START_ATTACK_REGION))
    if not button:
        return False
    task.log_info(f"the fight is waiting on its Attack button, pressing it (match {button.confidence:.2f})")
    # `click_box` waits a second after the click itself.
    task.click_box(button)
    return True


def key_at(left_x, count):
    """Say which key plays the card whose name starts at a given point, from where the hand puts each card.

    Upstream gives the leftmost card it read key 1 and counts on from there, which is wrong whenever OCR missed the
    real first card - a lowered hand read as its one raised card, the fourth, and pressed 1 for a minute.

    Args:
        left_x: The left edge of the card's name, as a screen fraction, from `_hand_cards`.
        count: The hand size the hand counter reads.

    Returns:
        The key as a string, or None for a card beyond the ninth.
    """
    if count <= 1:
        return "1"
    first, last = HAND_SPAN.get(count, WIDEST_SPAN)
    slot = min(max(round((left_x - first) / (last - first) * (count - 1)), 0), count - 1)
    return str(slot + 1) if slot < MAX_KEY else None


def padded(image, zoom):
    """Enlarge the Action Point digit and pad it out with black, without which OCR does not find it.

    Args:
        image: The digit, cut from the frame by `task.ocr`.
        zoom: How many times to enlarge it, from `POINTS_ZOOMS`.

    Returns:
        The enlarged digit inside a black border.
    """
    margin = POINTS_MARGIN * zoom
    return cv2.copyMakeBorder(cv2.resize(image, None, fx=zoom, fy=zoom), margin, margin, 2 * margin, 2 * margin, cv2.BORDER_CONSTANT, value=(0, 0, 0))


def points_left(task, frame):
    """Read how many Action Points the turn has left.

    Args:
        task: The running task, for its OCR.
        frame: The frame to read, from `frame_of`.

    Returns:
        The points, or None when no read is sure.
    """
    for zoom in POINTS_ZOOMS:
        read = [box.name.strip() for box in task.ocr(*POINTS_DIGIT, frame=frame, threshold=POINTS_SURE, frame_processor=lambda image: padded(image, zoom)) or []]
        if len(read) == 1 and len(read[0]) == 1 and read[0].isdigit():
            return int(read[0])
    return None


def out_of_points(task):
    """Say whether the game has just refused a card for want of Action Points.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True while the game's "Not enough AP." toast is up.
    """
    return text_in_region(task, NO_POINTS, NO_POINTS_REGION) is not None


def attribute_handler(utils):
    """Build the handler that answers the pick between created cards with the one the card picker rates highest.

    Args:
        utils: The loaded `utils` module, for its card reader and click.

    Returns:
        The handler.
    """

    def handle_attribute_choice(task):
        """Take the best of the created cards on offer.

        Args:
            task: The running task, whose `all_texts` is the current screen.

        Returns:
            True when a card was taken.
        """
        if not text_in_region(task, ATTRIBUTE_CHOICE, ATTRIBUTE_CHOICE_REGION):
            return False
        offered = utils.recognize_cards(task, page="attribute choice")
        if not offered:
            return False
        state = cards.Board(health=board.team_after_hit(frame_of(task)))
        named = [(cards.described(card["name"], card["description"]), card) for card in offered]
        name, card = max(named, key=lambda pair: cards.value(pair[0], state))
        task.log_info(f"choosing {name} of {[each for each, _ in named]}")
        utils._move_and_click(task, card["x"], card["y"])
        task.sleep(AFTER_KEY)
        return True

    return handle_attribute_choice


def shown_cost(task, frame, box, printed):
    """Read a hand card's cost off the screen when an effect has lowered it.

    Args:
        task: The running task, for its OCR.
        frame: The frame to read, from `frame_of`.
        box: The card's cost digit, from `board.cost_digit`.
        printed: What the data says the card costs, from `cards.cost`.

    Returns:
        The lowered cost, or None when the digit is not drawn lowered or reads no lower than the data.
    """
    if printed in (0, cards.X_COST) or not board.cost_lowered(frame, box):
        return None
    if printed == 1:
        # OCR seldom reads a lone 0, and a lowered 1 can only be one.
        return 0
    read = ego.DIGITS.search("".join(text.name for text in task.ocr(*box, frame=frame, frame_processor=ego.enlarged) or []))
    if read is None:
        return printed - 1
    return int(read.group()) if int(read.group()) < printed else None


def priced(task, utils_sortie, hand):
    """Give each hand card an effect has lowered the cost it shows, since the data only knows the printed one.

    Args:
        task: The running task, on a battle screen.
        utils_sortie: Upstream's Sortie module, for the name boxes the hand was read from.
        hand: Hand cards as `_hand_cards` reads them, with canonical names.

    Returns:
        The hand, each lowered card carrying its shown cost as `cost`.
    """
    frame = frame_of(task)
    names = {box.x / task.width: box for box in utils_sortie._hand_card_names(task) or []}
    shown_hand = []
    for card in hand:
        box = names.get(card.get("left_x"))
        printed = cards.cost(card["name"])
        shown = None if box is None else shown_cost(task, frame, board.cost_digit(card["left_x"], (box.y + box.height / 2) / task.height), printed)
        if shown is not None:
            logger.debug(f"{card['name']} shows {shown} AP, lowered from {printed}")
            card = {**card, "cost": shown}
        shown_hand.append(card)
    return shown_hand


def note_hand_read(task, utils_sortie):
    """Remember whether this frame's hand read came up empty while the counter still showed cards.

    A card the turn cannot afford is drawn lowered, below the band upstream reads names in. So is every card for a
    moment after a play or a deal, and upstream ends the turn on an empty read either way.

    Args:
        task: The running task, which the note is parked on.
        utils_sortie: Upstream's Sortie module, for its hand counter and name reader.

    Returns:
        The hand size the counter read, or None when it read nothing.
    """
    count = utils_sortie._read_hand_count(task)
    if not count:
        return count
    if utils_sortie._hand_card_names(task):
        setattr(task, UNREAD_HAND, None)
        setattr(task, BLIND, None)
    elif getattr(task, UNREAD_HAND, None) is None:
        setattr(task, UNREAD_HAND, 0)
    return count


def watch_invulnerable(task, turn):
    """Read whether an enemy is invulnerable, logging each change.

    It runs every battle frame, since a boss can turn invulnerable partway through a turn on crossing a health threshold.

    Args:
        task: The running task, on a battle screen.
        turn: The battle's `Turn`, which keeps the reading for the Ego planner and the picker.
    """
    invulnerable = board.enemy_invulnerable(frame_of(task))
    if invulnerable != turn.invulnerable:
        turn.invulnerable = invulnerable
        task.log_info("an enemy is invulnerable this turn, holding attacks that only deal damage" if invulnerable
                      else "no enemy is invulnerable any more, attacking again")


def handle_cards_left(task):
    """Cancel the end of a turn once the game says a card can still be played, when the bot may have missed one.

    That is an end upstream called on an unread hand, or one the picker called holding cards it passed over for cost.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when the end was called back. False leaves the check to upstream's centre Confirm, which is how an end
        the picker chose on purpose still goes through.
    """
    callbacks = getattr(task, UNREAD_HAND, None)
    unread = callbacks is not None and callbacks < CALLBACKS
    turn = getattr(task, TURN, None)
    priced_out = turn is not None and turn.priced_out and not turn.objected
    if not (unread or priced_out) or not text_in_region(task, CARDS_LEFT, CARDS_LEFT_REGION):
        return False
    cancel = text_in_region(task, CANCEL, CANCEL_REGION)
    if not cancel:
        return False
    if unread:
        task.log_info("the game says cards can still be played, so the hand was not raised yet - cancelling the end of turn")
        setattr(task, UNREAD_HAND, callbacks + 1)
    else:
        task.log_info(f"the game says a card can still be played, so one of {turn.priced_out} must cost less than the data says")
        turn.objected = True
    if turn is not None:
        turn.ended = False
    # `click_box` waits a second after the click itself, so a second wait here only held up the cards left to play.
    task.click_box(cancel)
    return True


def press_unread(task, count):
    """Try the hand's keys blind once the game has said a card can still be played but the hand still reads empty.

    Live, a 0 AP card stayed unread over its holographic art while every other card sat lowered out of the name band.

    Args:
        task: The running task, which the presses and the callback count are parked on.
        count: The hand size the hand counter reads.

    Returns:
        True when a key was pressed. Once every key has been tried, the game's next check is left to confirm.
    """
    callbacks = getattr(task, UNREAD_HAND, None)
    if not count or not callbacks or callbacks >= CALLBACKS:
        return False
    last = getattr(task, BLIND, None) or Blind(count, None, frozenset(), True)
    refused = last.refused
    if last.key and not last.confirmed:
        if not out_of_points(task):
            confirm(task)
            setattr(task, BLIND, last._replace(confirmed=True))
            return True
        task.log_info(f"not enough AP for key {last.key}, so it is not confirmed")
        refused |= {last.key}
    elif last.key and count < last.count:
        # The last key played, so every card right of it slid one key left. A drawn card joins on the right, so it moves nothing.
        refused = frozenset(key for key in refused if int(key) < int(last.key))
    elif last.key:
        refused |= {last.key}
    key = unread_key([], count, refused)
    if key is None:
        setattr(task, UNREAD_HAND, CALLBACKS)
        return False
    task.log_info(f"the game says a card can still be played but none of {count} reads, trying key {key}")
    task.send_key(key)
    task.sleep(AFTER_KEY)
    setattr(task, BLIND, Blind(count, key, refused, False))
    return True


def unheld_texts(task):
    """Read the screen without the hand cards a kit is keeping, for a prompt that takes the first card it finds.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        The OCR boxes, less any kept card inside `PROMPT_HAND`.
    """
    kept = kept_boxes([box for box in task.all_texts if in_region(box, PROMPT_HAND, task.width, task.height)])
    return [box for box in task.all_texts if id(box) not in kept]


def prompt_progress(task, utils_sortie):
    """Read upstream's hand prompt off the screen: how many cards it has and how many it asks for.

    Args:
        task: The running task, whose `all_texts` is the current screen.
        utils_sortie: Upstream's Sortie module, for its `find_box_at_point`.

    Returns:
        A `(chosen, need, to_top)` triple, `to_top` True when the cards go to the top of the Draw Pile, or None when this is
        not the prompt or its counter will not read.
    """
    caption = utils_sortie.find_box_at_point(task, *PROMPT_CAPTION)
    total = utils_sortie.find_box_at_point(task, *HAND_COUNTER)
    if not (caption and PROMPT_ASKS.search(caption.name) and total and HAND_TOTAL.search(total.name)):
        return None
    read = PROGRESS.search("".join(box.name for box in task.ocr(*PROMPT_PROGRESS) or []))
    return (int(read.group(1)), int(read.group(2)), PROMPT_TOP in caption.name) if read else None


def giving_up_order(name, box, kept, board_now, to_top=False):
    """Order the hand cards a prompt could take: dealt-to-you cards first, cards a kit keeps last, the rest by what they do.

    A card sent to the top of the Draw Pile is drawn again next turn, so there the order flips: the most expensive card first, since it
    is the one this turn's Action Points are least likely to cover, then the best of those, and a dealt-to-you card last.

    Args:
        name: The card's canonical name.
        box: The OCR box of its name.
        kept: The `id` of every box a kit is keeping, from `kept_boxes`.
        board_now: A `cards.Board` to rate the card against.
        to_top: Whether the prompt sends the card to the top of the Draw Pile, from `prompt_progress`.

    Returns:
        A sort key, the card best taken being smallest.
    """
    dealt = cards.category(name) in cards.DEALT_TO_YOU
    rating = cards.rated(name, board_now)
    if to_top:
        # A card that spends every Action Point left costs the most of all.
        price = cards.cost(name)
        return id(box) in kept, dealt, -(math.inf if price == cards.X_COST else price), -rating
    return id(box) in kept, not dealt, rating


def boost_order(played):
    """Rank the hand for a prompt that boosts a card, if the card that opened it is one that does.

    Args:
        played: The card whose key was pressed last, from `Turn.attempted`, or None.

    Returns:
        A sort key over `(name, board)`, the card best boosted being smallest, or None when the prompt gives a card up.
    """
    text = cards.description(played) if played else ""
    read = BOOST.search(text)
    if read is None:
        return None
    kind = read["kind"].strip().lower()
    owner = cards.owner(played)
    retain = "Retain effect" in text

    def order(name, board_now):
        if read["own"]:
            # Creations such as Orlea's Swiftie carry no owner in the data, so an unowned card may be the unit's own.
            fits = cards.owner(name) in (owner, None)
        elif kind == "attack":
            fits = cards.category(name) == cards.ATTACK_CATEGORY
        else:
            fits = kind in name.lower()
        return (not fits, retain and RETAIN_LINE not in cards.description(name), cards.category(name) in cards.DEALT_TO_YOU,
                -cards.rated(name, board_now))

    return order


def prompt_cards(task, texts):
    """Pick out the hand cards a hand prompt shows.

    Args:
        task: The running task, for the frame size.
        texts: OCR boxes, from the full-screen pass or a read of `PROMPT_HAND`.

    Returns:
        `(name, box)` for every box inside `PROMPT_HAND` that names a known card.
    """
    named = [(cards.canonical(box.name), box) for box in texts if in_region(box, PROMPT_HAND, task.width, task.height)]
    return [(name, box) for name, box in named if name in cards.CARD_COST]


def answer_prompt(task, utils_sortie, chosen, need, to_top=False):
    """Tap the card the hand can best spare, or confirm once the prompt's own counter says enough are chosen.

    A prompt is taken to be giving a card up - to the discard pile, the Draw Pile or Exhaust - unless it sends it to the top of the Draw Pile,
    or the card just played boosts the one picked.

    Args:
        task: The running task, which the prompt's progress is parked on.
        utils_sortie: Upstream's Sortie module, for its `_move_and_click`.
        chosen: How many cards the prompt's counter reads as chosen.
        need: How many it asks for.
        to_top: Whether the cards go to the top of the Draw Pile, which takes the best card rather than the worst.

    Returns:
        True when the frame was spent tapping or waiting, False once `PROMPT_TAPS` frames pass with no change, for upstream's random pick to try.
    """
    prompt = getattr(task, PROMPT, None)
    if prompt is None:
        prompt = Prompt()
        setattr(task, PROMPT, prompt)
    if chosen > prompt.chosen and prompt.tapped is not None:
        prompt.picked.append(prompt.tapped)
        prompt.taps = 0
    prompt.chosen = chosen
    if chosen >= need:
        task.log_info(f"hand prompt reads {chosen}/{need}, confirming")
        setattr(task, PROMPT, None)
        utils_sortie._move_and_click(task, *PROMPT_CONFIRM)
        task.sleep(1)
        return True
    # Under a prompt's glow the full-screen pass can miss every name in the hand, which a read of the hand alone still finds.
    hand = prompt_cards(task, task.all_texts) or prompt_cards(task, task.ocr(*PROMPT_HAND) or [])
    for picked in prompt.picked:
        taken = next((card for card in hand if card[0] == picked), None)
        if taken is not None:
            hand.remove(taken)
    if prompt.taps >= PROMPT_TAPS:
        task.log_info(f"hand prompt reads {chosen}/{need} after {prompt.taps} tries, leaving it to upstream's random pick")
        setattr(task, PROMPT, None)
        return False
    prompt.taps += 1
    if not hand:
        prompt.tapped = None
        task.log_info(f"hand prompt reads {chosen}/{need} but no card in hand reads yet, waiting")
        task.sleep(1)
        return True
    board_now = cards.Board(hand=tuple(name for name, _ in hand))
    turn = getattr(task, TURN, None)
    boost = boost_order(turn.attempted if turn else None)
    if boost:
        prompt.tapped, box = min(hand, key=lambda card: boost(card[0], board_now))
        doing = "boosting"
    else:
        kept = kept_boxes([box for _, box in hand])
        prompt.tapped, box = min(hand, key=lambda card: giving_up_order(*card, kept, board_now, to_top))
        doing = "moving to the top" if to_top else "giving up"
    task.log_info(f"hand prompt reads {chosen}/{need}, {doing} {prompt.tapped}")
    x, y = centre_of(box, task.width, task.height)
    utils_sortie._move_and_click(task, x, y + CARD_BODY)
    task.sleep(1)
    return True


def kit_waiting(task, utils_sortie, count):
    """Let a kit hold the turn while the game is about to change the hand by itself.

    An empty read straight after a wait keeps waiting too: a hand reads empty mid-fusion, and upstream ends the turn on one.

    Args:
        task: The running task, which the turn is parked on.
        utils_sortie: Upstream's Sortie module, for its hand reader.
        count: The hand size the counter read.

    Returns:
        True when this frame is spent waiting, capped at `KIT_WAIT` a turn so a change that never comes cannot stall it.
    """
    turn = getattr(task, TURN, None)
    if turn is None:
        return False
    names = [cards.canonical(card["name"]) for card in utils_sortie._hand_cards(task) or []]
    kit = kits.waiting(names, count) if names and count else None
    still = turn.kit_waited and not names and 0 < (count or 0) <= turn.hand_count
    turn.kit_waited = (kit is not None or still) and turn.kit_waits < KIT_WAIT
    if not turn.kit_waited:
        return False
    turn.kit_waits += 1
    task.log_info(f"{kit.name if kit else 'still'} waiting on the hand {names} ({turn.kit_waits}/{KIT_WAIT})")
    task.sleep(KIT_PAUSE)
    return True


def met(task, read):
    """Add the owner of every card read in hand to the party parked on the task.

    Args:
        task: The running task, which the party is parked on.
        read: The hand cards upstream read this frame, with their names as OCR spelled them.

    Returns:
        Every combatant whose card has been read so far, as a frozenset so `cards.canonical` can cache on it.
    """
    party = getattr(task, PARTY, frozenset()) | {cards.owner(cards.canonical(card["name"])) for card in read} - {None}
    setattr(task, PARTY, party)
    return party


def turn_of(task, hand_count):
    """Bring the per-turn bookkeeping up to date and hand it back.

    Args:
        task: The running task, which the state is parked on.
        hand_count: The hand size read this frame.

    Returns:
        The `Turn` in progress, fresh when the hand has just been dealt again.
    """
    turn = getattr(task, TURN, None)
    fight = fight_of(task)
    if turn is None or turn.fight != fight:
        turn = Turn(hand_count, fight=fight)
        setattr(task, TURN, turn)
    elif new_turn(turn.hand_count, hand_count, turn.ended):
        # With no node to tell fights apart, the battle is only known back to the turn before.
        earlier = (*turn.earlier, *turn.played) if fight is not None else turn.played
        turn = Turn(hand_count, turn.played, turn.hand, earlier, fight)
        setattr(task, TURN, turn)
    turn.hand_count = hand_count
    return turn


def end_of_turn(task):
    """Note that end turn was pressed, which settles the card tried last as played since upstream only ends an empty hand.

    Args:
        task: The running task, which the turn is parked on.
    """
    turn = getattr(task, TURN, None)
    if turn is None:
        return
    if turn.attempted is not None:
        turn.played.append(turn.attempted)
        if turn.attempted in turn.hand:
            turn.hand.remove(turn.attempted)
        turn.attempted = None
    turn.ended = True


def noting_end_of_turn(task):
    """Wrap a task's `send_key` so an end turn upstream presses closes the picker's turn too.

    Args:
        task: The running task.

    Returns:
        A stand-in for `task.send_key` that notes an end turn, then presses the key as the task would.
    """
    send_key = task.send_key

    def send(key, *args, **kwargs):
        if key == END_TURN_KEY:
            end_of_turn(task)
        return send_key(key, *args, **kwargs)

    return send


def install():
    """Put the card picker in place of upstream's press-every-key fallback.

    `handle_battle_page` reaches `_try_all_card_keys` as a module global, which Python resolves when the call
    is made, so rebinding it on the module is enough. That leaves every other line of upstream's battle frame
    running exactly as it did. It has two callers, and rebinding takes over both - the other is the escape
    hatch upstream reaches for after a card the list *did* name has failed to play three times running, which
    is usually one there are no Action Points for, so choosing a different card beats flailing at every key.

    Runs once per task load, so it has to be safe to call again: a replacement already in place is left alone
    rather than wrapped in a second one.
    """
    utils = loaded("utils")
    utils_sortie = loaded("utils_sortie")
    if utils is None or utils_sortie is None:
        return
    # Before the guard below, so a mode list loaded after the picker went in still gets it. Story loads last.
    insert_before("handle_center_confirm", handle_cards_left)
    insert_before("handle_card_function_select", attribute_handler(utils))
    if getattr(utils_sortie._try_all_card_keys, "_en_picker", False):
        return
    blind_fallback = utils_sortie._try_all_card_keys
    read_names = utils_sortie._hand_card_names
    read_hand = utils_sortie._hand_cards

    def _hand_cards(task):
        """Read the hand, keying it by where each card sits whenever OCR read fewer or more cards than the counter.

        Upstream counts keys on from the leftmost card it read, so a missed card shifts every key after it. Done
        here rather than in the picker, because upstream's Play Priority list and the battle recorder read keys
        from this too.

        Args:
            task: The running task.

        Returns:
            The hand cards as upstream reads them, with their keys corrected when the read came up short.
        """
        hand = read_hand(task)
        count = utils_sortie._read_hand_count(task)
        if count and any(str(card.get("key") or "").isdigit() and int(card["key"]) > count for card in hand):
            # A key past the hand size cannot exist, so text that is not a card got into the read. Live, a Bleed tooltip
            # was read as "Damage on" and "Combatants" in a hand of 4, pushing the real Bleed to key 9. The data names
            # every real card, so only what it knows is kept and keyed by position below.
            hand = [card for card in hand if cards.canonical(card["name"]) in cards.CARD_COST]
        if hand and count and len(hand) != count:
            hand = [{**card, "key": key_at(card["left_x"], count)} for card in hand]
            task.log_info(f"read {len(hand)} of {count} cards, so keys come from where each sits: "
                          f"{[(card['name'], card['key']) for card in hand]}")
        return hand

    def _hand_card_names(task):
        """Read the hand's card names once per OCR pass rather than once per caller.

        Upstream calls this twice a frame - directly, and again inside `_hand_cards` - and the picker would
        have made it three. Each call walks `all_texts` and logs a line for every box on screen, which on a
        battle screen is the noisiest thing the bot does.

        Args:
            task: The running task.

        Returns:
            The name boxes, from this frame's reading or the one already taken from the same OCR pass.
        """
        read_for, names = getattr(task, HAND_CACHE, (None, None))
        if read_for is task.all_texts:
            return names
        # Upstream prints one line per box on screen here, plus two summaries - about 26,700 lines of a
        # 244,000-line day. It is a debugging aid for its own region filter, shipped at info level, so it is
        # dropped to debug rather than removed: `python main_debug.py` still shows it when the filter misreads.
        with standing_in(task, log_info=logger.debug):
            names = read_names(task)
        setattr(task, HAND_CACHE, (task.all_texts, names))
        return names

    def _try_all_card_keys(task, count):
        """Play the best card in hand, in place of pressing every key in turn.

        Args:
            task: The running task.
            count: The hand size upstream read off the hand counter, which holds steady while OCR drops cards.
        """
        if not utils._get_config_value(task, SMART_CARD_PLAY, True):
            blind_fallback(task, count)
            return

        # Canonical, because OCR spells a name differently from frame to frame and a refusal has to match the
        # card it was about across them.
        read = utils_sortie._hand_cards(task) or []
        party = met(task, read)
        hand = priced(task, utils_sortie, kits.reading([{**card, "name": cards.canonical(card["name"], party, frozenset(cards.DECK))} for card in read], count))
        names = [card["name"] for card in hand]
        turn = turn_of(task, count)
        lost = unsettled(turn, names, count)
        if lost:
            task.log_info(f"read {names} without {lost} from the last frame, so the hand gets a frame to settle")
            task.sleep(KIT_PAUSE)
            return
        turn.hand = list(names)

        if turn.attempted is not None and not was_refused(turn.attempted, turn.attempted_copies, names):
            # Settled once, so a frame that returns before picking again cannot count the same play twice.
            turn.played.append(turn.attempted)
            turn.attempted = None
        elif turn.attempted is not None:
            turn.misses[turn.attempted] += 1
            # Live, Magnetic Field stayed in hand once with all three points to spend, and was given up on for the turn.
            # Once the game has said a card plays, each one tried is a guess, so a single miss is enough to move on.
            if turn.misses[turn.attempted] >= (1 if turn.objected else REFUSALS):
                turn.refused.add(turn.attempted)
                task.log_info(f"the game would not play {turn.attempted}, leaving it for the rest of this turn")

        # A turn whose count does not read is planned against a full three and corrected by what the game will actually accept.
        points = 0
        if board.has_action_points(task) and not out_of_points(task):
            read = points_left(task, frame_of(task))
            points = cards.BASE_ACTION_POINTS if read is None else read
        # An attack's flash can pass for extra counters, and an enemy that dies stays gone. Too few only values all-enemy damage as before.
        seen = len(board.enemy_counters(frame_of(task)))
        if seen:
            turn.enemies = min(turn.enemies or seen, seen)
        if turn.weakness is None:
            # Read once a turn, so this is also the one frame a turn to say what it opened holding.
            turn.weakness = board.weakness(task)
            against = f"enemies weak to {turn.weakness}" if turn.weakness else "no shared enemy weakness"
            budget = f"{points} Action Points to spend" if points else "no Action Points"
            task.log_info(f"turn opens with {budget}, {turn.enemies} enemy counter(s), {against}, hand {names}")
        state = cards.Board(action_points=points, weakness=turn.weakness, hand=tuple(names), played=tuple(turn.played),
                            last_turn=turn.last_turn, battle=(*turn.earlier, *turn.played), hand_size=count or 0, kept=turn.kept, invulnerable=turn.invulnerable, enemies=turn.enemies or 1,
                            health=board.team_after_hit(frame_of(task)))
        card = choose(hand, state, turn.refused)
        if card is None and turn.objected:
            # The game said a card is still playable, so the best of those passed over for cost is tried as if affordable.
            card = choose([held for held in hand if cards.price(held) > 0], state._replace(action_points=cards.BASE_ACTION_POINTS),
                          turn.refused)
        turn.priced_out = []
        if card is None:
            if not names:
                # Upstream ends an empty hand itself, so there is nothing here to do and nothing to say.
                return
            turn.attempted = None
            # A card OCR missed is still in hand. Live, an unread Cobalt Light was left behind with points to spend,
            # so each missing key is tried once before giving up on the turn.
            blind = unread_key(hand, count, turn.blind) if points else None
            if blind:
                task.log_info(f"read {len(names)} of {count} cards and none worth playing, trying unread key {blind}")
                turn.blind.add(blind)
                play_key(task, blind)
                return
            if not points:
                turn.priced_out = [name for name in names if cards.cost(name) > 0 and name not in turn.refused]
            spent = "" if points else ", no Action Points left"
            task.log_info(f"nothing left worth playing in {names}{spent}, ending the turn")
            end_of_turn(task)
            task.send_key(END_TURN_KEY)
            task.sleep(AFTER_KEY)
            return

        name = card["name"]
        task.log_info(f"playing {name} for {cards.price(card)} AP on key {card['key']}, "
                      f"worth {cards.value(name, state):.0f}")
        turn.attempted = name
        turn.attempted_copies = names.count(name)
        play_key(task, card["key"])

    original_page = utils_sortie.handle_battle_page

    def handle_battle_page(task):
        """Start a fight still waiting on its Attack button, otherwise run upstream's battle frame with the Ego choice answered from the screen.

        Args:
            task: The running task.

        Returns:
            True when the Attack button was pressed, otherwise whatever upstream's own handler returns.
        """
        if start_attack(task, utils_sortie):
            return True
        count = note_hand_read(task, utils_sortie)
        if kit_waiting(task, utils_sortie, count) or press_unread(task, count):
            return True
        turn = getattr(task, TURN, None)
        if count is None and turn is not None:
            # Off the battle screen, which is also how a fight won by a card ends without anyone pressing end turn.
            turn.ended = True
        if count:
            turn = turn_of(task, count)
            if getattr(task, TEAM_WANTED, False) and not (turn.played or turn.attempted):
                setattr(task, TEAM_WANTED, False)
                return True
            watch_invulnerable(task, turn)
            if ego.take_turn(task, utils_sortie, turn):
                return True
        with standing_in(utils_sortie, random=EgoChoice(task, utils_sortie.random)), standing_in(task, send_key=noting_end_of_turn(task)):
            return original_page(task)

    replace("handle_battle_page", handle_battle_page)
    original_hand_select = utils_sortie.handle_battle_hand_select
    original_return = utils_sortie.handle_return_to_draw_pile

    def handle_battle_hand_select(task):
        """Answer the hand prompt card by card against its own counter, or run upstream's random pick among the cards no kit is keeping.

        Args:
            task: The running task.

        Returns:
            True when this frame answered the prompt, otherwise whatever upstream's own handler returns.
        """
        progress = prompt_progress(task, utils_sortie)
        if progress is not None and answer_prompt(task, utils_sortie, *progress):
            return True
        with standing_in(utils_sortie, random=KeepHeld(utils_sortie.random)):
            return original_hand_select(task)

    def handle_return_to_draw_pile(task):
        """Run upstream's return-to-draw-pile prompt, which takes the leftmost card, over a hand without the cards a kit is keeping.

        Args:
            task: The running task.

        Returns:
            Whatever upstream's own handler returns.
        """
        with standing_in(task, all_texts=unheld_texts(task)):
            return original_return(task)

    replace("handle_battle_hand_select", handle_battle_hand_select)
    replace("handle_return_to_draw_pile", handle_return_to_draw_pile)

    # Marked so a later task load recognises the replacement and does not wrap it in itself.
    _try_all_card_keys._en_picker = True
    utils_sortie._try_all_card_keys = _try_all_card_keys
    utils_sortie._hand_card_names = _hand_card_names
    utils_sortie._hand_cards = _hand_cards
    # Upstream's own card-name filter excludes the type label printed under each card, but it lists only the
    # Chinese labels. On the Global client they are drawn in English, so every one of them passed straight
    # through and was read as a card in hand. Wrapped rather than replaced: the catalog rewrites some English
    # labels back into Chinese, and upstream's list is what catches those.
    reads_as_card = utils_sortie._is_card_name

    def _is_card_name(name):
        """Say whether a reading off the hand names a card, in either language.

        Args:
            name: The text the reader returned for one hand card.

        Returns:
            True when both upstream's filter and this fork's agree it is a card.
        """
        return bool(reads_as_card(name)) and cards.is_card_name(name)

    utils_sortie._is_card_name = _is_card_name
    logger.info("sortie battles now pick a card instead of pressing every key")


def auto_locked(task):
    """Say whether the fight shows the padlock of one that does not allow Auto, remembering it through a shaded prompt.

    Args:
        task: The running task, whose frame is the battle screen.

    Returns:
        True when the last plainly drawn Auto button was the padlock, or when none has been drawn plainly yet.
    """
    patch = patch_of(frame_of(task), AUTO_BUTTON)
    # The brightest channel is the HSV value, so this needs no conversion.
    if patch is not None and patch.size and patch.max() >= PLAIN_BUTTON:
        setattr(task, AUTO_LOCKED, colour_share(patch, LOCK_LOW, LOCK_HIGH) >= MIN_LOCK)
    return getattr(task, AUTO_LOCKED, True)


def unless_locked(auto_check):
    """Wrap Story's Auto handler so it lets a fight with Auto locked through to the borrowed screens.

    Args:
        auto_check: Story's `handle_battle_auto_check`, which turns Auto on and claims every battle frame.

    Returns:
        The replacement.
    """
    def handle_story_auto(task):
        if auto_locked(task):
            return False
        return auto_check(task)

    return handle_story_auto


def fight_story_battles():
    """Have Story mode play the battles that lock the game's Auto with Sortie's screens, and leave Auto to the rest."""
    utils_sortie = loaded("utils_sortie")
    utils_story = loaded("utils_story")
    if utils_sortie is None or utils_story is None:
        return
    names = [getattr(handler, "__name__", "") for handler in utils_story.PAGE_HANDLERS]
    index = next((at for at, name in enumerate(names) if name.startswith(AUTO_CHECK)), None)
    if index is None:
        return
    # Taken from Sortie's list rather than the module, so Story gets the card picker `install` put there.
    screens = [handler for handler in utils_sortie.PAGE_HANDLERS if getattr(handler, "__name__", "") in BATTLE_SCREENS]
    utils_story.PAGE_HANDLERS[index:index + 1] = [unless_locked(utils_story.PAGE_HANDLERS[index]), *screens]
    logger.info(f"story battles with Auto locked now play with Sortie's screens: {[handler.__name__ for handler in screens]}")


def apply():
    """Have the card picker stand in for upstream's fallback, and Story fight its own battles, once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    register(fight_story_battles)
    _patched = True
