"""Take the most valuable option an Unidentified Area offers, instead of ending the event.

Upstream chooses in this order: an option in the upper half of the option band is clicked outright, then the
blacklist and the user's priority lists, then the combat option, then a random pick. A logged Chaos run shows
what that means in practice - the upper-half shortcut fired 38 times and **chose "End the event" five times**,
the random pick fired 40 times, and the user's own priority list never ran once.

So two things change here: the options that give nothing are withheld while anything else is on offer, and
what is left is ranked spark, then rewards, then combat.

"Nothing" covers two kinds of option. Ending the event is one. Reading lore is the other, and it is worse:
the screen comes back unchanged afterwards, so the shortcut takes the same option again on the next frame. A
logged Chaos run clicked "Examine the mushroom" three times in four seconds, left the event, came back to it
and did the same thing again.

Both changes are made by wrapping `handle_event_task` and adjusting what it sees, rather than copying its two
hundred lines. Everything it does still runs untouched - the taskreward and treasure features, the
forbidden-event filter, the blacklist, and the user's priority lists, which are honoured ahead of the ranking.

The keyword lists come from the client's own data (`encounter_option_eff@eff_description@*`), where
"End the event" and "Initiate Battle" are fixed literals shared by 134 and 174 options.
"""

import re

from ok import Logger

from src.en.handlers import StandIn, loaded, register, replace

logger = Logger.get_logger(__name__)

# Ranks, best first. Descriptions are folded to lower case before matching, so these are lower case too.
SPARK = ("epiphany", "闪光")
QUIT = ("end the event",)
ATTACK = ("initiate battle", "event encounter")
# An option that only reads out lore. This phrasing was captured from a run rather than read out of the
# client's tables, so it is one known wording and not the whole set.
DIALOGUE = ("check information on",)

SPARK_RANK = 0
REWARD_RANK = 1
ATTACK_RANK = 2
QUIT_RANK = 3
# Worse than quitting. Ending the event at least moves the run on, while reading lore puts the same screen
# straight back up.
DIALOGUE_RANK = 4

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


def rank(description):
    """Score how much an event option is worth taking, lowest first.

    Plain containment on purpose. The OCR boxes behind a description arrive in an unpredictable order, so
    anything positional would rank the same option differently between frames, and `is_subsequence` - which
    upstream uses for the user's own keywords - matches characters in order and is far too loose on English.

    Args:
        description: The option text.

    Returns:
        `SPARK_RANK`, `REWARD_RANK`, `ATTACK_RANK`, `QUIT_RANK` or `DIALOGUE_RANK`.
    """
    text = fold(description)
    if contains(text, SPARK):
        return SPARK_RANK
    if contains(text, DIALOGUE):
        return DIALOGUE_RANK
    if contains(text, QUIT):
        return QUIT_RANK
    if contains(text, ATTACK):
        return ATTACK_RANK
    # Anything unrecognised counts as a reward. Most options naming no known marker still hand something over,
    # and ranking them below a battle would trade a real gain for a fight.
    return REWARD_RANK


def drop_unwanted(options):
    """Withhold the options that give nothing, unless they are all that is on offer.

    This is what makes "never end or stall the event while something else is available" a guarantee rather than
    a preference. Upstream's upper-half shortcut runs before any ranking and cannot be reasoned with, so those
    options are kept out of its reach entirely.

    Args:
        options: Every recognised option.

    Returns:
        The options worth considering.
    """
    if not options:
        return options
    ranked = [(rank(option.get("description", "")), option) for option in options]
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


def order(options, priority_keywords, is_subsequence):
    """Sort options so the best one is first.

    Upstream's upper-half shortcut takes the first option it can, before the blacklist or the user's lists are
    ever consulted. Sorting here is what lets that shortcut pick well, and it restores the precedence upstream
    intended: the user's own keywords first, in their configured order, then the ranking.

    Args:
        options: The options to sort.
        priority_keywords: The user's configured keywords, best first.
        is_subsequence: Upstream's matcher, so configured keywords behave exactly as they always have.

    Returns:
        A new list, best first. Equal entries keep their original order.
    """
    def key(numbered):
        index, option = numbered
        description = option.get("description", "")
        for position, keyword in enumerate(priority_keywords):
            if keyword and is_subsequence(keyword, description):
                return (0, position, index)
        return (1, rank(description), index)

    return [option for _, option in sorted(enumerate(options), key=key)]


class RankingChoice(StandIn):
    """Stands in for the `random` module for one call, ranking event options instead of picking blindly.

    Upstream reaches for `random.choice` once its own ladder has run out of opinions, which is the decision
    worth improving and the only `random` call inside the function. Anything that is not a list of event
    options falls through to the real module, so an unrelated call still behaves normally.
    """

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
        best = min(rank(option["description"]) for option in options)
        candidates = [option for option in options if rank(option["description"]) == best]
        # Ties stay random so a repeated event does not always take an identical path.
        chosen = self.original.choice(candidates)
        logger.info(f"ranked {len(options)} options, {len(candidates)} tied at rank {best}, taking: "
                    f"{chosen['description']}")
        return chosen


def apply():
    """Rank event options wherever `handle_event_task` is registered."""
    global _patched
    if _patched:
        return

    def install():
        utils = loaded("utils")
        if utils is None:
            return

        original_handle_event_task = utils.handle_event_task
        original_recognize = utils.recognize_event_options

        def ranked_recognize(task, *args, **kwargs):
            options = original_recognize(task, *args, **kwargs)
            if not options:
                return options
            priority = []
            for slot in range(1, 4):
                priority.extend(utils._get_card_list(task, f"装备{slot}号位优先级"))
            priority.extend(utils._get_card_list(task, "任务优先级"))
            return order(drop_unwanted(options), priority, utils.is_subsequence)

        def patched_handle_event_task(task):
            original_find_feature = task.find_feature
            original_random = utils.random

            def find_feature(feature_name=None, *args, **kwargs):
                # Hiding this one feature stops combat being clicked before anything is ranked. Set on the
                # instance, so it lasts one call, and find_one() goes through self.find_feature too.
                if feature_name == "attack_event":
                    return []
                return original_find_feature(feature_name, *args, **kwargs)

            task.find_feature = find_feature
            utils.random = RankingChoice(original_random)
            utils.recognize_event_options = ranked_recognize
            try:
                return original_handle_event_task(task)
            finally:
                utils.recognize_event_options = original_recognize
                utils.random = original_random
                del task.find_feature

        patched_handle_event_task._en_ranked = True
        replace("handle_event_task", patched_handle_event_task)

    register(install)
    _patched = True
