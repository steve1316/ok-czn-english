"""Write down what the game's own Auto AI does, so the fork's picker can be measured against it.

Sortie has no Auto button, which is why the fork picks cards itself. Chaos has one and upstream already
switches it on, so Chaos is the same game played by a reference implementation, on a screen the bot already
reads once a second. Watching it costs one more read of what is already there.
"""

import json
import os
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
from ok import Box, Logger

from src.en import board
from src.en.handlers import loaded, register, replace
from src.en.screen import patch_of

logger = Logger.get_logger(__name__)

# Where the recording goes. `data/` is already in `.gitignore`, so nothing here can reach a commit, and the
# file is append-only text that can be deleted at any time without breaking anything.
RECORDING = "data/auto_play.jsonl"
# How often to look while a battle is on screen. Auto plays several cards a second, and at upstream's one
# second pace a fifth of the readings lost two or more cards at once, which says nothing about which it chose
# first. The executor sleeps whatever is left of the interval, so asking for less than one OCR pass takes just
# means every pass is used. Only battle frames are sped up: the menus keep upstream's pace and its timing.
BATTLE_INTERVAL = 0.4
# Where upstream's own pace is parked the first time it is seen, so it can be handed back exactly rather than
# guessed at. Reading it off the task beats hardcoding one second, which is upstream's to change.
NORMAL_INTERVAL = "_en_normal_interval"
# Hand grabs taken between the main loop's own reads. The loop is OCR-bound at ~0.4s a frame and Auto plays faster than
# that, so in debug runs one thread saves just the hand and another reads the saves back once the battle is over.
BURST_DIR = "data/auto_burst"
# Kept apart from `RECORDING` because these lines only carry the hand. `study_auto.py` merges the two by time.
BURST_RECORDING = "data/auto_burst.jsonl"
# Seconds between grabs. A grab and its JPEG cost ~20ms, so what limits this is the read-back after the battle.
BURST_INTERVAL = 0.1
# The part of the frame worth keeping, as (x1, y1, x2, y2) fractions. Card names sit at 0.683-0.831 with their key
# digits ~0.05 above, and the hand counter reads at (0.509, 0.972).
BAND = (0.13, 0.6, 0.87, 1.0)
# Seconds after the last battle frame that a battle still counts as on screen. The main loop reads one every ~0.4s.
LIVE_FOR = 2.0
# Share of thumbnail pixels that must move for a grab to count as a new hand. The same figure `capture_window.py`
# measured on idle screens, where an animated background still moves a few percent.
SAME_HAND = 0.02
# How far a thumbnail pixel must move, out of 255, to count as moved.
MOVED = 24
# The (width, height) a band is shrunk to before two grabs are compared.
THUMBNAIL = (148, 40)
# High enough that OCR reads a saved band as it would the live frame.
JPEG_QUALITY = 90

_patched = False
# What the recorder has already said it could not do, so each failure is logged once rather than one hiding another.
_complained = set()


def complain(error, doing):
    """Log the recorder's first failure at one thing and nothing after it.

    A recorder that cannot write costs data, and saying so every frame would cost the log.

    Args:
        error: The exception that was swallowed.
        doing: What the recorder was trying to do, for the log line.
    """
    if doing not in _complained:
        logger.error(f"could not {doing}: {error}", exception=error)
        _complained.add(doing)


def band_origin(width, height):
    """Find where the saved band starts in the full frame.

    Args:
        width: The full frame's width in pixels.
        height: The full frame's height in pixels.

    Returns:
        The band's left and top edges in pixels.
    """
    return int(BAND[0] * width), int(BAND[1] * height)


def fingerprint(band):
    """Shrink a band to a small greyscale image for comparing grabs.

    Args:
        band: A hand band cut from a grabbed frame.

    Returns:
        A float array, cheap to diff against the last one kept.
    """
    return cv2.cvtColor(cv2.resize(band, THUMBNAIL, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)


def read_back(task, engine, band, at):
    """Read one saved band the way the live loop would have read the full frame.

    The boxes are moved into full-frame coordinates and handed to upstream's own hand reader on a stand-in, so the
    regions, key pairing and count readout are the live ones.

    Args:
        task: The running task, for its frame size and its OCR text fixes.
        engine: The read-back thread's own OCR engine, never the one the main loop is using.
        band: A saved hand band.
        at: When the band was grabbed, from its file name.

    Returns:
        A record holding `at`, `hand` and `count`, in the shape `seen` writes.
    """
    utils, utils_sortie = loaded("utils"), loaded("utils_sortie")
    left, top = band_origin(task.width, task.height)
    origin = Box(left, top, 1, 1)
    boxes = []
    for pos, (text, confidence) in engine.ocr(band)[0] or []:
        width, height = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
        if width <= 0 or height <= 0:
            continue
        # None below the confidence threshold, the same filter the live OCR applies.
        box = task.get_box(origin, confidence, height, pos, 1, text, task.ocr_default_threshold, width)
        if box:
            boxes.append(box)
    task.fix_texts(boxes)
    screen = SimpleNamespace(all_texts=utils._simplify_texts(boxes), width=task.width, height=task.height, log_info=lambda *_, **__: None)
    hand = utils_sortie._hand_cards(screen) or []
    return {"at": at, "hand": [[card.get("name"), card.get("key")] for card in hand], "count": utils_sortie._read_hand_count(screen)}


class Burst:
    """Grab the hand many times a second during a battle, and read the grabs back once it is over."""

    def __init__(self):
        self.task = None  # the running task, set on every battle frame. None until the threads start
        self.live_until = 0.0  # `time.time()` past which no battle is on screen

    def battle_seen(self, task):
        """Mark a battle as on screen, starting the threads the first time.

        Args:
            task: The running task, whose capture method the grabs go through.
        """
        first = self.task is None
        self.task = task
        self.live_until = time.time() + LIVE_FOR
        if first:
            os.makedirs(BURST_DIR, exist_ok=True)
            threading.Thread(target=self.grab, name="auto-burst-grab", daemon=True).start()
            threading.Thread(target=self.read, name="auto-burst-read", daemon=True).start()

    def live(self):
        """Say whether a battle is on screen.

        Returns:
            True until `LIVE_FOR` seconds after the last battle frame.
        """
        return time.time() < self.live_until

    def grab(self):
        """Save a hand band every `BURST_INTERVAL` while a battle is on, skipping ones that look like the last."""
        last = None
        while True:
            time.sleep(BURST_INTERVAL)
            if not self.live():
                last = None
                continue
            try:
                last = self.grab_once(last)
            except Exception as error:
                complain(error, "grab the hand")

    def grab_once(self, last):
        """Grab one frame and save its band, unless it looks like the last one saved.

        The capture method is shared with the main loop. BitBlt and WGC both hold their own lock around a grab.

        Args:
            last: The fingerprint of the last band saved, or None for the first grab of a battle.

        Returns:
            The fingerprint of the last band saved, after this grab.
        """
        at = time.time()
        band = patch_of(self.task.executor.method.get_frame(), BAND)
        if band is None:
            return last
        thumbnail = fingerprint(band)
        if last is not None and np.mean(np.abs(last - thumbnail) > MOVED) < SAME_HAND:
            return last
        cv2.imwrite(f"{BURST_DIR}/{at:.3f}.jpg", band, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        return thumbnail

    def read(self):
        """Read saved bands back oldest first, pausing whenever a battle comes back on screen."""
        engine = None
        while True:
            time.sleep(1)
            try:
                names = [] if self.live() else sorted(os.listdir(BURST_DIR))
                if not names:
                    continue
                # Its own engine, since the main loop's is not safe to call from two threads on OpenVINO.
                engine = engine or self.task.executor._create_ocr_lib("default")
                with open(BURST_RECORDING, "a", encoding="utf-8") as recording:
                    for name in names:
                        if self.live():
                            break
                        path = os.path.join(BURST_DIR, name)
                        # A file cut short when the app closed mid-write reads as None, and is dropped like the rest.
                        band = cv2.imread(path)
                        if band is not None:
                            recording.write(json.dumps(read_back(self.task, engine, band, float(name[:-4]))) + "\n")
                        os.remove(path)
            except Exception as error:
                complain(error, "read the hand grabs back")


BURST = Burst()


def seen(task):
    """Read one battle frame into the record that gets written down.

    Args:
        task: The running task.

    Returns:
        A dict of what the screen showed, ready to serialise.
    """
    utils_sortie = loaded("utils_sortie")
    hand = utils_sortie._hand_cards(task) or [] if utils_sortie else []
    frame = board.frame_of(task)
    # The game's own readout, not the length of what the reader found. When the two disagree the hand region
    # picked up something that is not a card, and that is the only way to tell a junk frame from a real one.
    count = utils_sortie._read_hand_count(task) if utils_sortie else None
    return {
        "at": round(time.time(), 3),
        "hand": [[card.get("name"), card.get("key")] for card in hand],
        "count": count,
        "points": board.has_action_points(task),
        "weakness": board.weakness(task),
        "egos": board.affordable_egos(task),
        "enemies": len(board.enemy_counters(frame)),
    }


def write(task):
    """Append one frame's record to the recording.

    Args:
        task: The running task.
    """
    with open(RECORDING, "a", encoding="utf-8") as recording:
        recording.write(json.dumps(seen(task)) + "\n")


def install():
    """Watch Chaos battles without changing what they do.

    This changes no behaviour: upstream's handler runs first and its answer is returned untouched, so Chaos plays
    exactly as it did whether the recorder works, fails, or is deleted. A failure inside it is logged once and
    swallowed for the same reason - losing data is cheap and losing a run is not.

    Runs once per task load, so it has to be safe to call again: a wrapper already in place is left alone
    rather than wrapped in a second one.
    """
    utils_chaos = loaded("utils_chaos")
    if utils_chaos is None:
        return
    original = getattr(utils_chaos, "handle_battle_auto_check", None)
    if original is None:
        return

    def watching(task):
        """Run upstream's Chaos battle frame, then write down what was on screen.

        Args:
            task: The running task.

        Returns:
            Whatever upstream's own handler returns, untouched.
        """
        on_battle = original(task)
        # Captured before the first change, so what gets handed back is upstream's own figure.
        if not hasattr(task, NORMAL_INTERVAL):
            setattr(task, NORMAL_INTERVAL, task.trigger_interval)
        # Restored the moment the battle leaves the screen, so nothing else in the run is paced differently.
        task.trigger_interval = BATTLE_INTERVAL if on_battle else getattr(task, NORMAL_INTERVAL)
        if on_battle:
            try:
                write(task)
                # Debug runs only. The extra grabs and a second OCR engine are a study aid a release run has no use for.
                if getattr(task, "debug", False):
                    BURST.battle_seen(task)
            except Exception as error:
                complain(error, "record the battle frame")
        return on_battle

    # A distinct name is what makes installing twice a no-op, the same way `rewards.py` wraps a handler:
    # `replace` matches on `__name__`, so once the list holds this there is nothing named after the original
    # left for a later install to wrap again. The module attribute is deliberately left alone, since the
    # handler lists are what the modes actually run.
    watching.__name__ = f"{original.__name__}_recording"
    if replace("handle_battle_auto_check", watching):
        logger.info(f"recording what Auto plays to {RECORDING}")


def apply():
    """Watch Chaos battles once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
