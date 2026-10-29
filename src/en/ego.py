"""Fire Sortie's Ego skills when they help, instead of at random once the EP bar is full.

Upstream fires one of the three Egos at random only when the bar is full, partway through a turn, so a buff lands after the attacks it
was for and a heal goes off whether the team needs it or not. This previews each Ego once ever to read what it does, then fires a guard
before a hit the team cannot take and a set-up ahead of the attacks, and spends a full bar on whatever fits the moment.
"""

import collections
import json
import os
import re

import cv2
import numpy as np
from ok import Logger

from src.en import board, cards
from src.en.game_battle import CARD_EXHAUSTS
from src.en.screen import centre_of, frame_of, in_region, lines_in, patch_of, raw_ocr, text_in_region

logger = Logger.get_logger(__name__)

# Every Ego read so far, kept across runs so each is previewed only once. `data/` is in `.gitignore`, and deleting the file only costs
# the previews. The panel moves Egos between slots as they are used, so an Ego is known by its portrait rather than its key.
EGO_FILE = "data/egos.json"
# Well over every partner and combatant in the game.
MAX_KNOWN = 200
# Decimals a saved signature keeps, which is far finer than `SAME_EGO` can tell apart.
SAVED_DECIMALS = 4
# Where a slot's portrait sits relative to its cost badge, and the size of the signature it is boiled down to.
PORTRAIT_X = (0.078, 0.135)
PORTRAIT_Y = (-0.015, 0.050)
SIGNATURE_SIZE = (16, 8)
# A portrait this flat is not one, such as a frame with the panel covered.
FLAT_PORTRAIT = 4.0
# How closely two signatures have to correlate to be the same Ego. One portrait measured 0.95-1.00 against itself, but 0.71 against its
# greyed-out look while the bar could not pay for it, and Owen's against Khalipe's 0.69. So each look is learnt as its own entry.
SAME_EGO = 0.85
# How long a preview card takes to open, and where on screen its label is looked for. A partner's card says "Partners" under the
# name and a combatant's says "Ego Skill", which OCR often cuts to "Ego Skil". The card moves with the length of its text.
PREVIEW_WAIT = 1
PREVIEW_AREA = (0.15, 0.25, 0.95, 0.82)
PREVIEW_LABELS = ("Partners", "Ego Ski")
# Where the name and effect text sit from the label's centre. On Legato of Faith the name is 0.04 above it and the text runs from 0.06
# to 0.13 below it, within 0.05 either side. Neither reaches left of `PREVIEW_AREA`, where the EP counters and Cancel sit.
CARD_HALF_WIDTH = 0.15
NAME_ABOVE = 0.06
TEXT_BELOW = 0.30
# The Cancel button the selected slot turns into, and where it sits from that slot's badge when OCR misses it.
CANCEL = "Cancel"
EGO_PANEL = (0.0, 0.62, 0.20, 0.98)
CANCEL_AT = (0.105, 0.014)
AFTER_CANCEL = 0.5
# Upstream's own keys and timings for firing an Ego.
CONFIRM_KEY = "enter"
AFTER_FIRE = 4
# The team readout along the top: HP as "1850/3116", and the shield as a lone number right of it.
TEAM_READOUT = (0.10, 0.0, 0.50, 0.08)
TEAM_HP = re.compile(r"(\d+)\s*/\s*(\d+)")
SHIELD_FROM_X = 0.40
# What an Ego is for, read from its effect text.
GUARD = "guard"
STRIKE = "strike"
SETUP = "set-up"
GUARDS = re.compile(r"Heal|Shield|Damage Reduction", re.I)
STRIKES = re.compile(r"Damage(?!\s*(?:Amount|Reduction))", re.I)
# A heal lands at once, so an Ego with one is fired as a set-up only for a hurt team, not at full HP for its Morale.
HEALS = re.compile(r"\bHeal", re.I)
# An Ego that does nothing unless a card is Exhausted, as Activate Defense Module's "when a card is Exhausted, 1 Weaken".
ON_EXHAUST = re.compile(r"\bExhausted\b", re.I)
SETUPS = re.compile(r"Morale|Fortitude|Vulnerable|Weaken|Draw|Critical|Increase|Counterattack|Mark|\bAP\b", re.I)
# A guard is fired once the next hit would leave the team below this share of its HP, and a full bar prefers one below the second.
GUARD_BELOW = 0.30
HURT_BELOW = 0.50
# How many Egos one turn may fire, so a misread bar cannot spend a whole turn firing.
FIRES_PER_TURN = 2
# Upstream's end-turn button, which says the turn is the player's to act in.
FINISH_TURN = "finishturn"
FINISH_TURN_REGION = (0.844, 0.782, 0.998, 0.990)
# The full-frame pass misses a cost badge's digit, so a badge is read on its own, enlarged this much. Offline, both of two captures read.
BADGE_ZOOM = 3
# The breakdown card that can end the fight outright, which would waste an Ego fired ahead of it.
ESCAPE_CARD = "Fear"
DIGITS = re.compile(r"\d+")
# Set by upstream once the run reaches its last boss.
BOSS = "final_boss_battle"

# The `(signature, Ego)` pairs from `EGO_FILE`, loaded on first use.
_known = None
# Signatures of portraits whose preview did not read this session, so a slot is not previewed again every turn.
_unread = []
# The unknown portrait each slot showed when last looked at, by key.
_sighted = {}

Ego = collections.namedtuple("Ego", [
    # The name on the preview card, or None when its label did not read.
    "name",
    # What it is for, a frozenset of `GUARD`, `STRIKE` and `SETUP`.
    "roles",
    # The effect text as read off the preview card.
    "text",
])


def roles_of(text):
    """Say what an Ego is for from its effect text.

    Args:
        text: The effect text read off its preview card.

    Returns:
        A frozenset of roles. A text that names no guard or damage is taken for a set-up.
    """
    roles = {role for role, words in ((GUARD, GUARDS), (STRIKE, STRIKES)) if words.search(text)}
    if not roles or SETUPS.search(text):
        roles.add(SETUP)
    return frozenset(roles)


def signature(frame, key):
    """Boil a slot's portrait down to a small normalised greyscale signature.

    Args:
        frame: The frame to read, or None when there is none.
        key: The slot's key, one of `board.EGO_KEYS`.

    Returns:
        A unit vector, or None when there is no frame, the slot is empty or it shows no portrait.
    """
    if not board.ego_in_slot(frame, key):
        return None
    middle = board.EGO_BADGE_Y[key]
    patch = patch_of(frame, (PORTRAIT_X[0], middle + PORTRAIT_Y[0], PORTRAIT_X[1], middle + PORTRAIT_Y[1]))
    if patch is None or patch.size == 0:
        return None
    grey = cv2.resize(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY), SIGNATURE_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    grey -= grey.mean()
    spread = float(np.linalg.norm(grey))
    if spread < FLAT_PORTRAIT * grey.size ** 0.5:
        return None
    return grey / spread


def known():
    """List every Ego read so far, loading the ones earlier runs saved on first use.

    Returns:
        The `(signature, Ego)` pairs, oldest first. Empty when nothing is saved or the file does not read.
    """
    global _known
    if _known is None:
        _known = []
        try:
            with open(EGO_FILE, encoding="utf-8") as saved:
                # Roles are worked out again from the text, so a change to the keywords reaches Egos learnt before it.
                _known = [(np.array(entry["signature"], dtype=np.float32), Ego(entry["name"], roles_of(entry["text"]), entry["text"]))
                          for entry in json.load(saved)]
        except FileNotFoundError:
            pass
        except Exception as error:
            logger.warning(f"could not read the saved Egos from {EGO_FILE}, previewing them again: {error}")
    return _known


def learn(mark, ego):
    """Remember an Ego by its portrait, and save it for later runs.

    Args:
        mark: Its portrait signature, from `signature`.
        ego: The `Ego` its preview read as.
    """
    global _known
    _known = (known() + [(mark, ego)])[-MAX_KNOWN:]
    try:
        os.makedirs(os.path.dirname(EGO_FILE), exist_ok=True)
        with open(EGO_FILE, "w", encoding="utf-8") as saved:
            json.dump([{"name": ego.name, "text": ego.text, "signature": [round(float(value), SAVED_DECIMALS) for value in mark]}
                       for mark, ego in _known], saved)
    except Exception as error:
        logger.warning(f"could not save the Egos to {EGO_FILE}, so the next run previews them again: {error}")


def recall(known, mark):
    """Find the Ego a portrait signature belongs to.

    Args:
        known: The `(signature, Ego)` pairs read so far, from `known`.
        mark: The signature to look up, or None.

    Returns:
        The Ego whose signature is closest, if close enough to be the same portrait, otherwise None.
    """
    if mark is None or not known:
        return None
    score, ego = max(((float(mark @ seen), ego) for seen, ego in known), key=lambda pair: pair[0])
    return ego if score >= SAME_EGO else None


def steady(key, mark):
    """Say whether a slot showed the same unknown portrait the last time it was looked at.

    A combatant's art sweeps over the panel for a moment when a card is played, and a portrait read through it would be saved as an Ego of
    its own.

    Args:
        key: The slot's key, one of `board.EGO_KEYS`.
        mark: The portrait signature it shows now, from `signature`.

    Returns:
        True when the last look agreed, so the portrait is worth a preview.
    """
    before = _sighted.get(key)
    _sighted[key] = mark
    return before is not None and float(mark @ before) >= SAME_EGO


def team_readout(task):
    """Read the team's HP and shield off the readout along the top.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        An `(hp, shield)` pair, the shield 0 when none is drawn, or None when the HP does not read.
    """
    hp, shield = None, 0
    for box in task.all_texts or []:
        if not in_region(box, TEAM_READOUT, task.width, task.height):
            continue
        read = TEAM_HP.search(box.name)
        if read:
            hp = int(read.group(1))
        elif box.name.strip().isdigit() and centre_of(box, task.width, task.height)[0] > SHIELD_FROM_X:
            shield = int(box.name.strip())
    return None if hp is None else (hp, shield)


def cancel_preview(task, utils, key):
    """Close an Ego's preview card without firing it.

    Args:
        task: The running task, whose `all_texts` holds a pass read with the preview open.
        utils: Upstream's Sortie module, for its `_move_and_click`.
        key: The slot whose preview is open.
    """
    cancel = text_in_region(task, CANCEL, EGO_PANEL)
    if cancel is not None:
        task.click_box(cancel)
    else:
        utils._move_and_click(task, CANCEL_AT[0], board.EGO_BADGE_Y[key] + CANCEL_AT[1])
    task.sleep(AFTER_CANCEL)


def identify(task, utils, key):
    """Open a slot's preview card, read what the Ego does, and close it again.

    Args:
        task: The running task.
        utils: Upstream's Sortie module, for its `_move_and_click`.
        key: The slot to read.

    Returns:
        The `Ego`, or None when no preview card opened or its text did not read.
    """
    task.send_key(key)
    task.sleep(PREVIEW_WAIT)
    raw_ocr(task)
    logger.debug(f"Ego preview on {key}: {[(box.name, *(round(at, 3) for at in centre_of(box, task.width, task.height))) for box in task.all_texts or []]}")
    label = next(filter(None, (text_in_region(task, word, PREVIEW_AREA) for word in PREVIEW_LABELS)), None)
    name, text = None, ""
    if label is not None:
        label_x, label_y = centre_of(label, task.width, task.height)
        left, right = max(label_x - CARD_HALF_WIDTH, PREVIEW_AREA[0]), label_x + CARD_HALF_WIDTH
        name = lines_in(task, (left, label_y - NAME_ABOVE, right, label_y - 0.01)) or None
        text = lines_in(task, (left, label_y + 0.01, right, min(label_y + TEXT_BELOW, PREVIEW_AREA[3])))
    if text or text_in_region(task, CANCEL, EGO_PANEL) is not None:
        cancel_preview(task, utils, key)
    return Ego(name, roles_of(text), text) if text else None


def decide(slots, banked, after_hit, invulnerable, attacking, boss, exhausting):
    """Choose the Ego to fire now, if any.

    The first rule that applies wins: a guard before a hit the team cannot take, a full bar spent on whatever fits, nothing into an
    enemy that cannot lose Health, then a set-up ahead of the attacks unless a boss fight is saving for a damage Ego. A set-up that heals
    waits for a hurt team.

    Args:
        slots: `(key, Ego or None, affordable)` for each slot, in panel order.
        banked: The EP the bar holds, from `board.banked_points`.
        after_hit: The share of HP the next hit leaves the team, from `board.team_after_hit`, or None when it did not read.
        invulnerable: Whether an enemy shows Absolute Invincibility this turn.
        attacking: Whether the hand holds an Attack card and Action Points to play it with.
        boss: Whether this is the run's final boss.
        exhausting: Whether the hand holds a card that Exhausts when played, from `CARD_EXHAUSTS`.

    Returns:
        A `(key, ego, reason)` triple, or None to fire nothing.
    """
    ready = [(key, ego) for key, ego, affordable in slots if affordable and ego is not None and (exhausting or not ON_EXHAUST.search(ego.text))]
    first = {role: next(((key, ego) for key, ego in ready if role in ego.roles), None) for role in (GUARD, STRIKE, SETUP)}
    hurt = after_hit is not None and after_hit < HURT_BELOW
    if after_hit is not None and after_hit < GUARD_BELOW and first[GUARD]:
        return (*first[GUARD], f"the next hit leaves the team at {after_hit:.0%}")
    if banked >= board.EP_MAX:
        order = (GUARD, SETUP, STRIKE) if invulnerable else (GUARD, STRIKE, SETUP) if hurt else (STRIKE, SETUP, GUARD)
        pick = next((first[role] for role in order if first[role]), None)
        return (*pick, "the EP bar is full") if pick else None
    if invulnerable or not attacking:
        return None
    saving = boss and any(ego is not None and STRIKE in ego.roles and not affordable for _, ego, affordable in slots)
    setup = next(((key, ego) for key, ego in ready if SETUP in ego.roles and (hurt or not HEALS.search(ego.text))), None)
    if saving or not setup:
        return None
    return (*setup, "ahead of the attacks")


def enlarged(image):
    """Enlarge a cost badge for OCR.

    Args:
        image: The badge, cut from the frame by `task.ocr`.

    Returns:
        The badge `BADGE_ZOOM` times the size.
    """
    return cv2.resize(image, None, fx=BADGE_ZOOM, fy=BADGE_ZOOM)


def read_digit(task, frame, box):
    """Read the number in a cost badge or a card's cost digit.

    Args:
        task: The running task, for its OCR.
        frame: The frame to read, from `frame_of`.
        box: Where the number sits, in screen fractions.

    Returns:
        The number, or None when OCR reads no digit.
    """
    read = DIGITS.search("".join(text.name for text in task.ocr(*box, frame=frame, frame_processor=enlarged) or []))
    return None if read is None else int(read.group())


def payable(task, frame, tinted, banked):
    """Narrow the slots with a tinted badge to those the bar can pay for.

    A reduced cost tints its badge whether or not the bar can pay, so each badge's cost is read and held against the bar. A badge that
    does not read is taken at its tint.

    Args:
        task: The running task, on a battle screen.
        frame: The frame to read the badges off, from `frame_of`.
        tinted: The slots `board.affordable_egos` found tinted.
        banked: The EP the bar holds, from `board.banked_points`.

    Returns:
        The keys of the slots that can be fired.
    """
    keys = set()
    if not banked:
        return keys
    for key in tinted:
        box = board.box_around(board.EGO_BADGE_X, board.EGO_BADGE_Y[key], board.EGO_BADGE_HALF)
        cost = read_digit(task, frame, box)
        if cost is None or cost <= banked:
            keys.add(key)
    return keys


def take_turn(task, utils, turn):
    """Fire an Ego when one helps right now, reading any Ego not yet seen first.

    Args:
        task: The running task, on a battle screen.
        utils: Upstream's Sortie module, for its hand reader and `_move_and_click`.
        turn: The battle's `Turn`, which counts the Egos fired and the slots that would not read.

    Returns:
        True when this frame was spent previewing or firing an Ego.
    """
    if turn.ego_fires >= FIRES_PER_TURN or not task.find_feature(feature_name=FINISH_TURN, box=task.box_of_screen(*FINISH_TURN_REGION)):
        return False
    hand = utils._hand_cards(task) or []
    if any(cards.canonical(card["name"]) == ESCAPE_CARD for card in hand):
        return False
    frame = frame_of(task)
    banked = board.banked_points(frame)
    affordable = payable(task, frame, board.affordable_egos(task), banked)
    seen = known()
    slots = []
    for key in board.EGO_KEYS:
        mark = signature(frame, key)
        ego = recall(seen, mark)
        # An Ego the bar cannot pay for cannot be fired, so it is not worth a preview yet.
        if ego is None and mark is not None and key in affordable and not any(float(mark @ failed) >= SAME_EGO for failed in _unread) and steady(key, mark):
            ego = identify(task, utils, key)
            if ego is None:
                task.log_info(f"the Ego on {key} did not preview, leaving it to upstream until the app restarts")
                _unread.append(mark)
            else:
                task.log_info(f"the Ego on {key} is {ego.name or 'unnamed'} ({', '.join(sorted(ego.roles))}): {ego.text}")
                learn(mark, ego)
            return True
        slots.append((key, ego, key in affordable))
    after_hit = board.team_after_hit(frame)
    invulnerable = turn.invulnerable
    attacking = board.has_action_points(task) and any(cards.category(cards.canonical(card["name"])) == cards.ATTACK_CATEGORY for card in hand)
    boss = bool(getattr(task, "node_status", {}).get(BOSS))
    exhausting = any(cards.canonical(card["name"]) in CARD_EXHAUSTS for card in hand)
    logger.debug(f"Egos {[(key, ego.name if ego else None, payable) for key, ego, payable in slots]}, EP {banked}, "
                 f"after the next hit {after_hit}, invulnerable {invulnerable}, attacking {attacking}, boss {boss}, exhausting {exhausting}")
    choice = decide(slots, banked, after_hit, invulnerable, attacking, boss, exhausting)
    if choice is None:
        if invulnerable and not turn.ego_held:
            task.log_info(f"an enemy is invulnerable this turn, holding EP {banked}")
            turn.ego_held = True
        return False
    key, ego, reason = choice
    return fire(task, utils, turn, key, ego, reason, banked)


def fire(task, utils, turn, key, ego, reason, banked):
    """Fire one Ego, first checking a pure guard's preview adds HP or shield.

    Args:
        task: The running task.
        utils: Upstream's Sortie module, for its `_move_and_click`.
        turn: The battle's `Turn`, which counts the Egos fired.
        key: The slot to fire.
        ego: The `Ego` on it.
        reason: Why, for the log.
        banked: The EP the bar held before the press, from `board.banked_points`.

    Returns:
        True, since the frame was spent either way.
    """
    before = team_readout(task) if ego.roles == {GUARD} else None
    task.send_key(key)
    task.sleep(PREVIEW_WAIT)
    if before is not None:
        raw_ocr(task)
        after = team_readout(task)
        if after is not None and after[0] <= before[0] and after[1] <= before[1]:
            task.log_info(f"{ego.name} would add nothing to HP {before[0]} and shield {before[1]}, cancelling it")
            cancel_preview(task, utils, key)
            turn.ego_fires += 1
            return True
    task.log_info(f"firing {ego.name or key} ({', '.join(sorted(ego.roles))}) {reason}")
    task.send_key(CONFIRM_KEY)
    task.sleep(AFTER_FIRE)
    # A press made while an attack or the turn's opening effects still play is ignored by the game, and the bar keeps its EP. One retry
    # covers that. A second miss means the game will not take it this turn, so the turn stops firing rather than pressing it again.
    if board.banked_points(frame_of(task)) < banked:
        turn.ego_fires += 1
        return True
    if not turn.ego_missed:
        task.log_info(f"{ego.name or key} did not take, EP still {banked}, so it does not count against the turn")
        turn.ego_missed = True
    else:
        task.log_info(f"{ego.name or key} did not take again, leaving the Egos alone for the rest of the turn")
        turn.ego_fires = FIRES_PER_TURN
    # A missed Ego stays selected, and upstream's end turn key does nothing past it.
    raw_ocr(task)
    if text_in_region(task, CANCEL, EGO_PANEL) is not None:
        cancel_preview(task, utils, key)
    return True
