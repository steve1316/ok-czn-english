"""Take the most valuable option an Unidentified Area offers, instead of ending the event.

Upstream chooses in this order: an option in the upper half of the option band is clicked outright, then the
blacklist and the user's priority lists, then the combat option, then a random pick. A logged Chaos run shows
what that means - the upper-half shortcut fired 38 times and chose "End the event" five times, the random pick
fired 40 times, and the user's own priority list never ran once.

So options that give nothing are withheld while anything else is on offer, and what is left is ranked spark,
then rewards, then combat. "Nothing" covers ending the event, and reading lore, which is worse: the screen
comes back unchanged afterwards, so the shortcut takes the same option again on the next frame. A logged run
clicked "Examine the mushroom" three times in four seconds, left the event, came back and did it again.

Both changes wrap `handle_event_task` and adjust what it sees rather than copying its two hundred lines.
Unopened Treasure Trove chests are clicked before upstream runs, since its chest template misses two of the
three and its shortcut ends the event first. Everything else still runs untouched - the taskreward feature, the
forbidden-event filter, the blacklist, and the user's priority lists, which are honoured ahead of the ranking. The keyword lists come
from the client's own data (`encounter_option_eff@eff_description@*`), where "End the event" and "Initiate
Battle" are fixed literals shared by 134 and 174 options.
"""

import re
from functools import lru_cache
from pathlib import Path

import cv2
from ok import Logger

from src.en import desire
from src.en.handlers import StandIn, loaded, register, wrap
from src.en.screen import frame_of, hsv_of, patch_of

logger = Logger.get_logger(__name__)

# Names this change in the shared record of what a function already carries, so it is applied once.
TAG = "ranked events"

# Ranks, best first. Descriptions are folded to lower case before matching, so these are lower case too.
SPARK = ("epiphany", "闪光")
QUIT = ("end the event",)
ATTACK = ("initiate battle", "event encounter")
# An option that only reads out lore. This phrasing was captured from a run rather than read out of the
# client's tables, so it is one known wording and not the whole set.
DIALOGUE = ("check information on",)
# An event handing out a Desire card says so. The faction is named separately, and both have to be present:
# "Claim" and "Control" are ordinary English words that turn up in options having nothing to do with Desire.
DESIRE = ("desire",)

SPARK_RANK = 0
# A Desire card of the faction the run is chasing. Below a spark, which permanently upgrades a card, and
# above an ordinary reward, because points in one faction compound towards a team-wide bonus at 3, 5 and 7.
DESIRE_RANK = 1
REWARD_RANK = 2
ATTACK_RANK = 3
# A Desire card of some other faction. The assign screen skips it, so it is worth nothing, and withholding it leaves
# the random-faction option, which can still land on the faction being chased.
OFF_FACTION_RANK = 4
QUIT_RANK = 5
# Worse than quitting. Ending the event at least moves the run on, while reading lore puts the same screen
# straight back up.
DIALOGUE_RANK = 6

# `_get_region_text` glues the OCR boxes together with no separator and in an unstable order, and the reader
# loses or invents spaces at line breaks - the same option was captured as "Spark an Epiphany for a" and
# "Spark an Epiphanyfor a". Dropping everything that is not a letter or digit makes those the same string.
INSIGNIFICANT = re.compile(r"[^\w%]+", re.UNICODE)

# A marker that folds away to nothing would be "in" every description and match everything, so each one
# has to survive folding. Two is the floor rather than four because a marker can legitimately be a
# two-character Chinese word: the catalog rewrites a box reading exactly "Epiphany" into "闪光" before a
# description is assembled, which is how Chinese reaches an otherwise English string.
MIN_MARKER_LENGTH = 2
# Latin markers have no such excuse - a two-letter fragment would match far too much, so they are
# written as whole phrases and held to a longer floor.
MIN_LATIN_MARKER_LENGTH = 4

# Upstream's `treasure` template: the download arrow drawn over an unopened chest, cropped in pixels from the
# image its annotations name. An opened chest loses the arrow, so every arrow still on screen is a chest to open.
TREASURE_IMAGE = Path(__file__).resolve().parents[2] / "ok_tasks" / "assets" / "images" / "0.png"
TREASURE_CROP = (1205, 481, 1268, 551)
# Where upstream looks for that arrow. It already spans all three chests, it just never matched two of them.
TREASURE_REGION = (0.477, 0.336, 0.841, 0.540)
# The template is the arrow on the gold pile behind the middle chest, and the side chests draw it on dark purple,
# so upstream's colour match scored them 0.648 and 0.675 against its 0.7 cutoff. Matching only the near-white
# pixels drops the background: the two arrows in `tests/images/treasure_band.png` score 0.731 and 0.795, while
# the best hit in the same region across 703 other captured frames is 0.550.
ARROW_MIN_SCORE = 0.65
ARROW_MAX_SATURATION = 60
ARROW_MIN_VALUE = 200
# Pixels between two hits for them to count as separate arrows. The chests sit ~530px apart, the arrow is 63px.
ARROW_SEPARATION = 60
# Chests are only opened on the event screen, which always offers "End the event" while any are left.
LEAVE_MARKERS = ("离开", *QUIT)

_patched = False


def fold(text):
    """Reduce a description to the form the markers are matched against.

    Args:
        text: The option text as `recognize_event_options` assembled it.

    Returns:
        The text, lower cased with punctuation and spacing removed.
    """
    return INSIGNIFICANT.sub("", (text or "").casefold())


def contains(text, markers):
    """Report whether any marker appears in an already-folded description.

    Args:
        text: The folded description.
        markers: The markers to look for, unfolded.

    Returns:
        True when at least one marker is present.
    """
    return any(fold(marker) in text for marker in markers)


def rank(description, target=None):
    """Score how much an event option is worth taking, lowest first.

    Plain containment on purpose. The OCR boxes behind a description arrive in an unpredictable order, so
    anything positional would rank the same option differently between frames, and `is_subsequence` - which
    upstream uses for the user's own keywords - matches characters in order and is far too loose on English.

    Args:
        description: The option text.
        target: The Desire faction the run is chasing, or None when it is not being tracked.

    Returns:
        `SPARK_RANK`, `DESIRE_RANK`, `REWARD_RANK`, `ATTACK_RANK`, `OFF_FACTION_RANK`, `QUIT_RANK` or `DIALOGUE_RANK`.
    """
    text = fold(description)
    if contains(text, SPARK):
        return SPARK_RANK
    if contains(text, DIALOGUE):
        return DIALOGUE_RANK
    if contains(text, QUIT):
        return QUIT_RANK
    if target and contains(text, DESIRE):
        if contains(text, (target,)):
            return DESIRE_RANK
        if contains(text, desire.FACTIONS):
            return OFF_FACTION_RANK
    if contains(text, ATTACK):
        return ATTACK_RANK
    # Anything unrecognised counts as a reward. Most options naming no known marker still hand something over,
    # and ranking them below a battle would trade a real gain for a fight.
    return REWARD_RANK


def drop_unwanted(options, target=None):
    """Withhold the options that give nothing, unless they are all that is on offer.

    This is what makes "never end or stall the event while something else is available" a guarantee rather than
    a preference. Upstream's upper-half shortcut runs before any ranking and cannot be reasoned with, so those
    options are kept out of its reach entirely.

    Args:
        options: Every recognised option.
        target: The Desire faction the run is chasing, or None.

    Returns:
        The options worth considering.
    """
    if not options:
        return options
    ranked = [(rank(option.get("description", ""), target), option) for option in options]
    # Every option worth taking ranks at `ATTACK_RANK` or better, so the cutoff only rises above it on a screen
    # offering nothing but ways to end or stall the event - and then only far enough to leave something to click.
    cutoff = max(min(tier for tier, _ in ranked), ATTACK_RANK)
    kept = [option for tier, option in ranked if tier <= cutoff]
    # Naming what was dropped, not just how many. The next lore wording to loop will be one nobody has seen
    # yet, and this line is what makes it obvious from a run's log rather than needing a repro.
    withheld = [f"rank {tier}: {option.get('description', '')}" for tier, option in ranked if tier > cutoff]
    if withheld:
        logger.info(f"withholding {len(withheld)} option(s) that give nothing - {' | '.join(withheld)}")
    return kept


def order(options, priority_keywords, is_subsequence, target=None):
    """Sort options so the best one is first.

    Upstream's upper-half shortcut takes the first option it can, before the blacklist or the user's lists are
    ever consulted. Sorting here is what lets that shortcut pick well, and it restores the precedence upstream
    intended: the user's own keywords first, in their configured order, then the ranking.

    Args:
        options: The options to sort.
        priority_keywords: The user's configured keywords, best first.
        is_subsequence: Upstream's matcher, so configured keywords behave exactly as they always have.
        target: The Desire faction the run is chasing, or None.

    Returns:
        A new list, best first. Equal entries keep their original order.
    """
    def key(numbered):
        index, option = numbered
        description = option.get("description", "")
        for position, keyword in enumerate(priority_keywords):
            if keyword and is_subsequence(keyword, description):
                return (0, position, index)
        return (1, rank(description, target), index)

    return [option for _, option in sorted(enumerate(options), key=key)]


def white_mask(patch):
    """Keep only the near-white pixels of a patch, so an icon matches whatever it is drawn over.

    Args:
        patch: The pixels to reduce, in BGR.

    Returns:
        A single-channel image, 255 where the pixel is near white and 0 elsewhere.
    """
    return cv2.inRange(hsv_of(patch), (0, 0, ARROW_MIN_VALUE), (180, ARROW_MAX_SATURATION, 255))


@lru_cache(maxsize=1)
def arrow_mask():
    """Build the arrow template once, from the same crop upstream matches in colour.

    Returns:
        The white mask of the arrow, or None when the image cannot be read.
    """
    image = cv2.imread(str(TREASURE_IMAGE))
    if image is None:
        logger.warning(f"could not read the treasure template from {TREASURE_IMAGE}")
        return None
    left, top, right, bottom = TREASURE_CROP
    return white_mask(image[top:bottom, left:right])


def find_chests(frame):
    """Find the arrows over the chests that have not been opened yet.

    Args:
        frame: The frame to read, or None when there is none.

    Returns:
        A list of `(x, y)` arrow centres in fractions of the frame, left to right. Empty when there is no frame.
    """
    patch = patch_of(frame, TREASURE_REGION)
    template = arrow_mask()
    if patch is None or template is None:
        return []
    scores = cv2.matchTemplate(white_mask(patch), template, cv2.TM_CCOEFF_NORMED)
    frame_height, frame_width = frame.shape[:2]
    template_height, template_width = template.shape
    left, top = TREASURE_REGION[0] * frame_width, TREASURE_REGION[1] * frame_height
    centres = []
    # Take the best hit, blank the arrow it sits on, and repeat until nothing left clears the cutoff.
    while True:
        _, best, _, (x, y) = cv2.minMaxLoc(scores)
        if best < ARROW_MIN_SCORE:
            break
        centres.append(((left + x + template_width / 2) / frame_width, (top + y + template_height / 2) / frame_height))
        scores[max(0, y - ARROW_SEPARATION):y + ARROW_SEPARATION, max(0, x - ARROW_SEPARATION):x + ARROW_SEPARATION] = -1
    return sorted(centres)


def offers_leave(task):
    """Report whether the frame's OCR shows the option that ends an event.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.

    Returns:
        True when "End the event", or the catalog's rewrite of it, is on screen.
    """
    return any(contains(fold(box.name), LEAVE_MARKERS) for box in getattr(task, "all_texts", None) or [])


def open_a_chest(task, utils):
    """Click the next unopened chest on a Treasure Trove screen.

    Upstream checks for chests only after its upper-half shortcut, which clicks "End the event" first whenever
    that option is detected high enough, so this has to run before upstream does.

    Args:
        task: The running task.
        utils: Upstream's `utils` module, for its `_move_and_click`.

    Returns:
        True when a chest was clicked.
    """
    if not offers_leave(task):
        return False
    chests = find_chests(frame_of(task))
    if not chests:
        return False
    x, y = chests[0]
    logger.info(f"{len(chests)} unopened chest(s) left, opening the one at ({x:.3f}, {y:.3f})")
    utils._move_and_click(task, x, y)
    task.sleep(2)
    return True


class RankingChoice(StandIn):
    """Stands in for the `random` module for one call, ranking event options instead of picking blindly.

    Upstream reaches for `random.choice` once its own ladder has run out of opinions, which is the decision
    worth improving and the only `random` call inside the function. Anything that is not a list of event
    options falls through to the real module, so an unrelated call still behaves normally.

    This is the path most event screens actually reach, so it has to be told which Desire faction the run is
    chasing. A live Chaos run ranked an option handing out the faction it wanted as an ordinary reward,
    because the sort that knew about factions was never the thing deciding.
    """

    def __init__(self, original, target=None):
        """Hold the module being stood in for, and the faction to steer towards.

        Args:
            original: The `random` module upstream would otherwise have used.
            target: The Desire faction the run is chasing, or None when it is not being tracked.
        """
        super().__init__(original)
        # Set here rather than lazily: `StandIn.__getattr__` would otherwise forward the lookup to `random`.
        self.target = target

    def choice(self, sequence):
        """Pick the best-ranked event option, or defer when this is not an event choice.

        Args:
            sequence: Whatever upstream is choosing between.

        Returns:
            One item from the sequence.
        """
        options = list(sequence)
        if not options or not all(isinstance(option, dict) and "description" in option for option in options):
            return self.original.choice(sequence)
        best = min(rank(option["description"], self.target) for option in options)
        candidates = [option for option in options if rank(option["description"], self.target) == best]
        # Ties stay random so a repeated event does not always take an identical path.
        chosen = self.original.choice(candidates)
        logger.info(f"ranked {len(options)} options, {len(candidates)} tied at rank {best}, taking: "
                    f"{chosen['description']}")
        return chosen


def ranking(utils):
    """Build the fork-local change to wrap `handle_event_task` in.

    Args:
        utils: Upstream's `utils` module, which the wrapper stands in on for the length of each call.

    Returns:
        A factory taking the handler currently installed and returning the one to run in its place.
    """
    def factory(original_handle_event_task):
        original_recognize = utils.recognize_event_options

        def ranked_recognize(task, *args, **kwargs):
            options = original_recognize(task, *args, **kwargs)
            if not options:
                return options
            priority = []
            for slot in range(1, 4):
                priority.extend(utils._get_card_list(task, f"装备{slot}号位优先级"))
            priority.extend(utils._get_card_list(task, "任务优先级"))
            target = desire.target_faction(task, utils)
            return order(drop_unwanted(options, target), priority, utils.is_subsequence, target)

        def patched_handle_event_task(task):
            if open_a_chest(task, utils):
                return True
            original_find_feature = task.find_feature
            original_random = utils.random
            target = desire.target_faction(task, utils)

            def find_feature(feature_name=None, *args, **kwargs):
                # Hiding this one feature stops combat being clicked before anything is ranked. Set on the
                # instance, so it lasts one call, and find_one() goes through self.find_feature too.
                if feature_name == "attack_event":
                    return []
                return original_find_feature(feature_name, *args, **kwargs)

            task.find_feature = find_feature
            utils.random = RankingChoice(original_random, target)
            utils.recognize_event_options = ranked_recognize
            try:
                return original_handle_event_task(task)
            finally:
                utils.recognize_event_options = original_recognize
                utils.random = original_random
                del task.find_feature

        return patched_handle_event_task

    return factory


def install(utils):
    """Rank event options wherever `handle_event_task` is registered.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_event_task", ranking(utils), TAG)


def apply():
    """Rank event options wherever `handle_event_task` is registered."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
