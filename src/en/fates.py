"""Choose which Fate to take on the "Choose your fate" screen, by a per-mode tier table.

Upstream picks at random from every line in the title region, so it can tap a description line, and it takes a Fate that adds a Curse or
one whose follow-up it skips as readily as a free Legendary weapon. Sortie and Chaos keep separate Fate tables, so each has its own tiers.
"""

from ok import Logger

from src.en.events import fold
from src.en.handlers import StandIn, loaded, register, standing_in, wrap
from src.en.screen import same_line

logger = Logger.get_logger(__name__)

TAG = "ranked fates"
SORTIE_MODE = "SortieMode"
# Tiers, best first. A title that matches nothing in its mode's table lands in `FAIR`.
GEAR, STRONG, FAIR, WEAK, AVOID = range(5)
# Every Sortie Fate, named as `game_fates.SORTIE_FATES` has them, by tier. `GEAR` hands over equipment at no cost. `STRONG` adds combat
# power for the rest of the run with nothing to set up. `WEAK` pays out only in a deck or a hand the run rarely has, or adds Stickiness.
# `AVOID` adds a Curse, Penance or Distrust, or opens a screen the bot cannot finish - `handle_convert_card` skips Convert Tactics' conversion.
SORTIE_TIERS = {
    GEAR: (
        "Armament of War", "Armor of the Protector", "Life's Accessory", "Divine Refinement", "Quicksupply", "It's Fine, No Problem",
        "Mastery: Distortion", "Mastery: Harmonization", "Collecting Distortions", "Collecting Harmonizations", "Rare Equipment Collector",
        "Rare Equipment Specialist", "Equipment Coming Soon",
    ),
    STRONG: (
        "Strengthen the Offensive", "Overflowing Waves", "Saffron Fate", "Ruddy Fate", "Cerulean Fate", "Deadly Intuition", "Steadfast Protection",
        "Exemplary Harmonization", "Unexpected Vigor", "Impulse Ignition", "Oblivion", "Fate Syntony", "Endless Greed", "Momentary Respite",
        "Physical Training", "Prismatic Fate", "Sekred's Inversion", "Diallos's Sigil",
    ),
    FAIR: (
        "A Promised Fate", "Alien Devourer", "Anarchic Reconstruction", "Bits N' Pieces", "Buoyancy", "Caligo's Blessing", "Call of the Unknown",
        "Chance to Resupply", "Cognitive Reconstruction", "Concentrated Offensive", "Critical Exhaust", "Dellang's Backing", "Destined Harmony",
        "Destiny of Gold", "Diallos's Blessing", "Diallos's Glory", "Decision Postponed", "Epiphanic Inspiration", "Epiphany Chain",
        "Equitable Trade", "Exemplary Duplicate", "Feeling Lighter", "Foundational Design", "Giant's Momentum", "Kyrken's Antinomy",
        "Kyrken's Blessing", "Kyrken's Oracle", "Limitless Proliferation", "Morale Boost", "Nihilum's Blessing", "Nihilum's Gaze",
        "Nihilum's Resonance", "Overflowing Insight", "Overload Insight", "Preparations", "Protection Stance", "Purple Fate", "Sacred Inspiration",
        "Seal of Duplication", "Seal of Removal", "Sekred's Blessing", "Sekred's Breath", "Steadfast Will", "Strengthen Fundamentals",
        "Summoning Contract", "Switching Grand-Scale Tactics", "Tempted By Silver", "The Even Protector", "The Odd Executor", "The VIP Special",
        "Tilting Scales", "Uncertain Contract", "Vytor's Blessing",
    ),
    WEAK: (
        "21", "Sole Adjudicator", "Awakened Taboo", "Abandon Curse", "Fork in a Road", "Grand Finale", "Rejecting Misfortune", "Icky Credits",
        "Uncanny Cycle", "Hasty Cleanup",
    ),
    AVOID: (
        "Convert Tactics", "Dangerous Steps", "Cursed Relic", "Cursed Inspiration", "The Price for Gold", "Twins of Fate", "Pilgrim's Path",
        "Faithless's Path",
    ),
}
# Every Chaos Fate, named as `game_fates.CHAOS_FATES` has them, by the same tiers. `GEAR` here includes the Fates that promise equipment from
# later rewards. `AVOID` takes a Curse, half the team's Health, the run's Credit rewards, or hands enemies a lasting edge.
CHAOS_TIERS = {
    GEAR: ("Research", "Self-Sustenance", "Revelation", "Hope", "Control", "Favor"),
    STRONG: ("Oracle", "Sympathy", "Diligence", "Envy", "Gaze", "Influence", "Cheerful", "Courtship", "Glory", "Persevere", "Pilgrim (Sekred)"),
    FAIR: (
        "Adapt", "Altruism", "Attunement", "Brainwash", "Causality", "Challenges", "Clarity", "Compulsion", "Conviction", "Cruelty", "Curiosity",
        "Deficiency", "Domination", "Dream", "Encouragement", "Enlightenment", "Exultation", "Friendship", "Hallucination", "Hunting",
        "Inference", "Inspiration", "Intolerance", "Laziness", "Leadership", "Liberation", "Lucid Dream", "Mistreatment", "Oblivion", "Passion",
        "Pilgrim (Diallos)", "Pilgrim (Kyrken)", "Pilgrim (Nihilum)", "Pilgrim (Vytor)", "Possession", "Prudence", "Radiance", "Regret",
        "Reminiscence", "Sacrifice", "Self-Control", "Subjugation", "Temerity", "Temptation", "Tranquility", "Voracity",
    ),
    WEAK: (
        "Abundance", "Breath", "Closure", "Focus", "Purification", "Silence", "Faithless (Diallos)", "Faithless (Kyrken)", "Faithless (Nihilum)",
        "Faithless (Sekred)", "Faithless (Vytor)",
    ),
    AVOID: ("Kleptomania", "Tenacity", "Greed", "Reverberation", "Loss"),
}
# Each mode's folded Fate names, mapped to their tier.
SORTIE_RANKS = {fold(name): tier for tier, names in SORTIE_TIERS.items() for name in names}
CHAOS_RANKS = {fold(name): tier for tier, names in CHAOS_TIERS.items() for name in names}

_patched = False


def rank(name, ranks):
    """Score a Fate by its name, lowest first.

    Args:
        name: The Fate's title as OCR read it.
        ranks: The running mode's folded names and tiers, `SORTIE_RANKS` or `CHAOS_RANKS`.

    Returns:
        The Fate's tier, or `FAIR` for a title the table does not know.
    """
    return ranks.get(fold(name), FAIR)


def titles(boxes):
    """Keep only the Fate names, which sit on one line above every description line.

    Args:
        boxes: Upstream's candidates, every OCR box in the title region.

    Returns:
        The boxes on the topmost line.
    """
    top = min(boxes, key=lambda box: box.y)
    return [box for box in boxes if same_line(top, box)]


class FateChoice(StandIn):
    """Stands in for `random` while upstream's Fate handler runs, so its one `random.choice` takes the best-ranked Fate name."""

    def __init__(self, original, ranks):
        """Hold the module being stood in for, and the running mode's tiers.

        Args:
            original: The `random` module upstream would otherwise have used.
            ranks: The running mode's folded names and tiers, `SORTIE_RANKS` or `CHAOS_RANKS`.
        """
        super().__init__(original)
        # Set here rather than lazily: `StandIn.__getattr__` would otherwise forward the lookup to `random`.
        self.ranks = ranks

    def choice(self, sequence):
        """Pick the best-ranked Fate name, at random among a tie.

        Args:
            sequence: Upstream's candidate OCR boxes.

        Returns:
            One of the boxes.
        """
        scored = [(rank(box.name, self.ranks), box) for box in titles(sequence)]
        best = min(score for score, _ in scored)
        chosen = self.original.choice([box for score, box in scored if score == best])
        logger.info(f"Fates on offer {[box.name for _, box in scored]}, taking {chosen.name}")
        return chosen


def choosing_fate(utils):
    """Build the change that wraps `handle_destiny_choice` in a ranked pick.

    Args:
        utils: Upstream's `utils` module, which the wrapper stands in on for the length of each call.

    Returns:
        A factory taking the handler currently installed and returning the one to run in its place.
    """
    def factory(handler):
        def handle_destiny_choice(task):
            ranks = SORTIE_RANKS if type(task).__name__ == SORTIE_MODE else CHAOS_RANKS
            with standing_in(utils, random=FateChoice(utils.random, ranks)):
                return handler(task)

        return handle_destiny_choice

    return factory


def install(utils):
    """Rank Fates wherever `handle_destiny_choice` is registered.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_destiny_choice", choosing_fate(utils), TAG)


def apply():
    """Rank Fates wherever `handle_destiny_choice` is registered."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
