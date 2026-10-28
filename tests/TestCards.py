"""Check which card the picker plays, and in what order.

Real card names throughout, so a reading that stops agreeing with the client's own data fails here rather
than in a run. `Anchor` and `Annihilation Shot` are the same card in every respect the picker reads - one
Action Point, an Attack, exactly "100% Damage" - except that Haru is Justice and Renoa is Void. That makes
them the fair pair for anything about attributes.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import cards, kits  # noqa: E402
from src.en.game_text import EPIPHANIES  # noqa: E402

JUSTICE_ATTACK = "Anchor"
VOID_ATTACK = "Annihilation Shot"
# Costs nothing, so only the Curse rule can keep it out of a plan.
CURSE = "Anemia"
# Costs nothing and even draws a card, and is still never worth playing.
AILMENT = "Anxiety"
# Free, and draws.
FREE_DRAW = "Adagio"
# One Action Point, and a Power card.
BUFF = "Arcane Rush"
# Free, and an Attack, so it separates "free first" from "setup first".
FREE_ATTACK = "Magnum Shot"
# Epiphanies that drop the Retain line Beryl's kit plays around: a Charged Shot that does not grow, and an Opening Found kept for its cost.
FLAT_CHARGED_SHOT = next(text for text in EPIPHANIES["Charged Shot"] if "Retain:" not in text)
FREE_OPENING_FOUND = next(text for text in EPIPHANIES["Opening Found"] if "Cost to 0" in text)
# Rin's deck from the live run: a First Form that takes Dark Mist Stance, and an Annihilation that cuts her other cards' cost in it.
RIN_DECK = {"Dark Mist Sword: First Form": next(text for text in EPIPHANIES["Dark Mist Sword: First Form"] if "Stance" in text),
            "Dark Mist Secret Art: Annihilation": next(text for text in EPIPHANIES["Dark Mist Secret Art: Annihilation"] if "Decrease Cost" in text)}
# Two Action Points for 220% damage, which is better value per point than 100% for one.
BIG_ATTACK = "Charge Launcher"
# Spends every Action Point left rather than a fixed number.
SPENDS_EVERYTHING = "Absolute Protection"
# Costs nothing and, now and then, ends the fight outright.
ESCAPE = "Fear"
# A free card the generic scoring rates above a Mental Breakdown card.
STURDIE = "Sturdie \u2605\u2605\u2605"


def hand(*names_in_order):
    """Build a hand the way `_hand_cards` hands one over.

    Args:
        names_in_order: Card names, left to right as they sit on screen.

    Returns:
        A list of hand-card dicts, each carrying the hotkey that plays it.
    """
    return [{"name": name, "key": str(index + 1)} for index, name in enumerate(names_in_order)]


def played(chosen):
    """Reduce a plan to the names it plays, in order.

    Args:
        chosen: The plan.

    Returns:
        The card names.
    """
    return [card["name"] for card in chosen]


class TestNeverPlayed(unittest.TestCase):
    """Cards the game deals you rather than ones you choose."""

    def test_a_curse_is_left_in_hand(self):
        self.assertNotIn(CURSE, played(cards.plan(hand(CURSE, JUSTICE_ATTACK), cards.Board())))

    def test_a_status_ailment_is_left_in_hand(self):
        self.assertNotIn(AILMENT, played(cards.plan(hand(AILMENT, JUSTICE_ATTACK), cards.Board())))

    def test_a_card_that_helps_while_held_stays_in_hand(self):
        # Unknown: Mutant Sample shows no cost, so the picker took it for a free card and would have pressed its key first.
        self.assertNotIn("Unknown: Mutant Sample", played(cards.plan(hand("Unknown: Mutant Sample", JUSTICE_ATTACK), cards.Board())))

    def test_a_hand_of_nothing_but_junk_plays_nothing(self):
        self.assertEqual(cards.plan(hand(CURSE, AILMENT), cards.Board()), [])


class TestAffordability(unittest.TestCase):
    """The Action Point budget, which upstream never knew anything about."""

    def test_a_plan_stays_inside_the_budget(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK, BUFF), cards.Board(action_points=2))
        spent = sum(cards.cost(card["name"]) for card in chosen)
        self.assertLessEqual(spent, 2)

    def test_a_free_card_is_played_whatever_the_budget(self):
        self.assertEqual(played(cards.plan(hand(FREE_DRAW), cards.Board(action_points=0))), [FREE_DRAW])

    def test_a_lowered_cost_is_what_gets_paid(self):
        # A card an effect has lowered to 0 is still playable with no points left.
        lowered = [{**card, "cost": 0} for card in hand(JUSTICE_ATTACK)]
        self.assertEqual(played(cards.plan(lowered, cards.Board(action_points=0))), [JUSTICE_ATTACK])

    def test_nothing_affordable_plays_nothing(self):
        self.assertEqual(cards.plan(hand(JUSTICE_ATTACK), cards.Board(action_points=0)), [])


class TestOrdering(unittest.TestCase):
    """The order a turn is played in, which is most of what separates good play from legal play."""

    def test_a_free_card_goes_before_one_that_costs_anything(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, FREE_ATTACK), cards.Board())
        self.assertEqual(played(chosen)[0], FREE_ATTACK)

    def test_a_buff_goes_before_an_attack(self):
        # An Upgrade buffs the rest of the battle, so it lands before the attack it improves and even before a free card.
        for other in (JUSTICE_ATTACK, FREE_ATTACK):
            with self.subTest(other=other):
                self.assertEqual(played(cards.plan(hand(other, BUFF), cards.Board())), [BUFF, other])

    def test_a_card_that_primes_the_next_attack_goes_before_it(self):
        # Both are Skills, which sorted them after the attack Wind Charge adds a hit to and Frost Charge's Vulnerable would have raised.
        for primer, attack in (("Wind Charge", "Downward Cut"), ("Frost Charge", JUSTICE_ATTACK)):
            with self.subTest(primer=primer):
                self.assertEqual(played(cards.plan(hand(attack, primer), cards.Board())), [primer, attack])

    def test_the_better_value_attack_goes_first(self):
        # 220% for two points beats 100% for one, and three points pays for both.
        chosen = cards.plan(hand(JUSTICE_ATTACK, BIG_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [BIG_ATTACK, JUSTICE_ATTACK])

    def test_a_cheap_card_does_not_crowd_out_a_better_one(self):
        # Spending a point on the cheap card would leave too little for the dear one. Which cards get played
        # has to be settled on what they are worth, and only then put in the order they are played in.
        cases = [
            # Live, Khalipe's Basic Lashing was bought first for its 100% per point, stranding the 2 points left after it.
            (hand("Lashing", "Vulture Ejection"), 3, ["Vulture Ejection"]),
        ]
        for cards_in_hand, points, expected in cases:
            with self.subTest(hand=played(cards_in_hand)):
                self.assertEqual(expected, played(cards.plan(cards_in_hand, cards.Board(action_points=points))))

    def test_a_tight_budget_buys_the_better_attack(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, BIG_ATTACK), cards.Board(action_points=2))
        self.assertEqual(played(chosen), [BIG_ATTACK])

    def test_damage_to_all_enemies_counts_once_per_enemy(self):
        # Live, Vulture Ejection's 120% to all enemies was valued as if it hit one.
        for enemies, expected in ((1, [JUSTICE_ATTACK]), (3, ["Diagonal Slash"])):
            with self.subTest(enemies=enemies):
                chosen = cards.plan(hand(JUSTICE_ATTACK, "Diagonal Slash"), cards.Board(action_points=1, enemies=enemies))
                self.assertEqual(expected, played(chosen))

    def test_every_hit_of_a_multi_hit_attack_counts(self):
        # 40% three times is 120%, which beats 100% once. Read as its first hit alone it lost to it. Fan of Daggers writes
        # its count before the word, "60% x 3 Damage", and was given up to a discard prompt as a 60% card.
        for attack in ("Aggressive Assault", "Fan of Daggers"):
            with self.subTest(attack=attack):
                chosen = cards.plan(hand(JUSTICE_ATTACK, attack), cards.Board(action_points=1))
                self.assertEqual(played(chosen), [attack])

    def test_a_retain_effect_is_not_counted_on_play(self):
        # Diallos's Declaration shields only when it is kept in hand, so playing it is worth its draw alone.
        self.assertEqual(cards.features("Diallos's Declaration"), cards.Features(damage=0, shield=0, draw=1))


class TestSpendsEverything(unittest.TestCase):
    """A card with no fixed price takes whatever is left, so it can only ever be played last."""

    def test_it_goes_after_a_card_with_a_price(self):
        chosen = cards.plan(hand(SPENDS_EVERYTHING, JUSTICE_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, SPENDS_EVERYTHING])

    def test_nothing_is_played_after_it(self):
        # Four points, so the two attacks costing three between them still leave it something to spend.
        chosen = cards.plan(hand(SPENDS_EVERYTHING, JUSTICE_ATTACK, BIG_ATTACK), cards.Board(action_points=4))
        self.assertEqual(played(chosen)[-1], SPENDS_EVERYTHING)

    def test_it_is_not_played_with_no_points_left(self):
        chosen = cards.plan(hand(SPENDS_EVERYTHING), cards.Board(action_points=0))
        self.assertEqual(chosen, [])


class TestWeakness(unittest.TestCase):
    """Matching the attribute an enemy is weak to, which is where most free damage in this game comes from."""

    def test_the_matching_attribute_goes_first(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board(weakness="Void"))
        self.assertEqual(played(chosen), [VOID_ATTACK, JUSTICE_ATTACK])

    def test_an_unknown_weakness_leaves_the_order_alone(self):
        # Nothing separates these two without a weakness to match, so the hand's own order has to survive.
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board())
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, VOID_ATTACK])

    def test_a_weakness_nobody_matches_leaves_the_order_alone(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, VOID_ATTACK), cards.Board(weakness="Passion"))
        self.assertEqual(played(chosen), [JUSTICE_ATTACK, VOID_ATTACK])


class TestEpiphany(unittest.TestCase):
    """A glowing card upgrades itself when played, which is worth more than one turn of damage."""

    def test_the_glowing_card_goes_first(self):
        chosen = cards.plan(hand(BIG_ATTACK, JUSTICE_ATTACK), cards.Board(epiphany=JUSTICE_ATTACK))
        self.assertEqual(played(chosen)[0], JUSTICE_ATTACK)

    def test_the_glowing_card_is_bought_before_a_bigger_one(self):
        # Two points buys either the 220% attack or the glowing one. The Epiphany is a permanent upgrade, so
        # it is worth more than the turn of damage it gives up.
        board = cards.Board(action_points=2, epiphany=JUSTICE_ATTACK)
        chosen = cards.plan(hand(BIG_ATTACK, JUSTICE_ATTACK), board)
        self.assertEqual(played(chosen), [JUSTICE_ATTACK])

    def test_a_chance_to_escape_comes_before_even_the_glowing_card(self):
        chosen = cards.plan(hand(FREE_ATTACK, JUSTICE_ATTACK, ESCAPE), cards.Board(epiphany=JUSTICE_ATTACK))
        self.assertEqual(played(chosen)[0], ESCAPE)

    def test_a_mental_breakdown_card_goes_first(self):
        # Live, Sturdie went twice and Drawing Slash once before an Impulse, though playing it is how the combatant recovers.
        for card in cards.BREAKDOWN_CARDS:
            with self.subTest(card=card):
                self.assertIn(card, cards.CARD_COST)
                self.assertEqual(played(cards.plan(hand(STURDIE, card), cards.Board()))[0], card)

    def test_a_glowing_curse_is_still_never_played(self):
        chosen = cards.plan(hand(CURSE, JUSTICE_ATTACK), cards.Board(epiphany=CURSE))
        self.assertNotIn(CURSE, played(chosen))


class TestTellingCardsFromLabels(unittest.TestCase):
    """The game prints a type label under every card, and the reader hands both back the same way."""

    def test_a_real_card_is_a_card(self):
        self.assertTrue(cards.is_card_name("Anchor"))

    def test_a_type_label_is_not_a_card(self):
        for label in ("Basic Attack", "Basic Skill", "Status Ailment", "Skill", "Attack"):
            with self.subTest(label=label):
                self.assertFalse(cards.is_card_name(label))

    def test_a_type_label_misread_by_one_letter_is_not_a_card(self):
        # "Attacl" and "Attach" were read off live hands, and the fold landed both on the card `Attack!`.
        for misread in ("Attacl", "Attach", "Jpgrade", "XAttacl", "Attad", "Basio", "Skiu", "△Skilll"):
            with self.subTest(misread=misread):
                self.assertFalse(cards.is_card_name(misread))

    def test_a_truncated_type_label_is_not_a_card(self):
        # "Basic Atta" was the single most common junk reading in a real Chaos recording.
        for stub in ("Basic Atta", "Status Ailm", "XBasic A", "Basic", "grade"):
            with self.subTest(stub=stub):
                self.assertFalse(cards.is_card_name(stub))

    def test_the_mental_breakdown_label_is_not_a_card(self):
        # Live readings of the label under a Mental Breakdown card. Each was keyed as a card of its own and shifted the keys after it.
        for reading in ("Mental Breakdown", "276Mental Breakdown", "ental Brea", "Mental Breal", "ntal Bre", "sreakdown"):
            with self.subTest(reading=reading):
                self.assertFalse(cards.is_card_name(reading))

    def test_the_chinese_label_the_catalog_rewrites_to_is_not_a_card(self):
        # `ocr.po` turns "Defense" into this, and upstream's own exclude list has no defense keyword, so it
        # reached the hand as a card name 22 times in one recording.
        self.assertFalse(cards.is_card_name("防御力"))

    def test_the_level_badge_is_not_a_card(self):
        for badge in ("@ Lv.", "等级"):
            with self.subTest(badge=badge):
                self.assertFalse(cards.is_card_name(badge))

    def test_a_tooltip_keyword_tag_is_not_a_card(self):
        # Read off live hands while a tooltip covered them, each counted as a card Auto played.
        for tag in ("[Unique / Bullet]", "[Ephemeral / Exhaust /", "Bullet]"):
            with self.subTest(tag=tag):
                self.assertFalse(cards.is_card_name(tag))

    def test_a_card_cut_short_to_something_label_like_is_still_a_card(self):
        # "Quant" is "Quantum Seed", and only one letter from the start of "Attack" once the type icon is trimmed off. "Accent" is
        # Mute Accent and one letter from the start of "Mental Breakdown" once two letters are trimmed off.
        for stub in ("Quant", "NA:Defens", "Accent"):
            with self.subTest(stub=stub):
                self.assertTrue(cards.is_card_name(stub))

    def test_a_card_whose_name_starts_with_a_label_is_still_a_card(self):
        # These are the ones a careless label test deletes. Each is a real card whose name begins with a type
        # label, so the known-card check has to run before the truncation test.
        for name in ("Curse of the Fairy", "Defense System", "Power Anchor", "Attack, My Minions"):
            with self.subTest(card=name):
                self.assertTrue(cards.is_card_name(name))

    def test_a_card_named_exactly_after_a_label_loses_to_the_label(self):
        # Only two cards collide this way and `ocr.po` already decided it: the label sits under every card of
        # its type, the card is one of 794. `Curse` costs nothing since curse cards are never played anyway.
        self.assertFalse(cards.is_card_name("Attack!"))
        self.assertFalse(cards.is_card_name("Curse"))

    def test_a_card_released_after_the_dump_is_still_a_card(self):
        self.assertTrue(cards.is_card_name("Some Card From A Later Patch"))


class TestReadingNames(unittest.TestCase):
    """What the reader hands over is rarely spelt the way the data spells it."""

    def test_a_name_run_together_is_still_recognised(self):
        chosen = cards.plan(hand("AnnihilationShot"), cards.Board())
        self.assertEqual(cards.cost("AnnihilationShot"), cards.cost(VOID_ATTACK))
        self.assertEqual(len(chosen), 1)

    def test_a_reading_resolves_to_the_card_it_can_only_be(self):
        """Every reading here is one the OCR pass actually produced, repaired only where it is unambiguous."""
        for description, reading, expected, *party in (
            ("case and spacing do not matter", "  anchor ", JUSTICE_ATTACK),
            # The hotkey is printed just above the card, close enough that the reader sometimes returns the
            # two as one box. A real Sortie hand came back with "1=Soul Riff" beside four cleanly read names.
            ("a hotkey run into the name is stripped", "1=Soul Riff", "Soul Riff"),
            # The reader truncates a name mid-word while the hand animates. "Knife Tos" was read 10 times in
            # one Chaos recording, and it can only ever have been one card.
            ("a name cut short is repaired", "Knife Tos", "Knife Toss"),
            # Two cards start this way, so guessing between them would be worse than not knowing.
            ("an ambiguous stub is left alone", "Attac", "Attac"),
            ("a stub too short to be sure is left alone", "Bas", "Bas"),
            # Tiphera's Archetypes, read hundreds of times in one Chaos recording without the glyph that names them.
            ("an Archetype keeps a glyph the reader kept", "hetype:△", "Archetype: △"),
            ("an Archetype read with an O for its circle", "Archetype:O", "Archetype: ○"),
            ("an Archetype that lost its glyph is still an Archetype", "Archetyp", "Archetype: ○"),
            ("an Archetype read with a v for its y", "chetvpe", "Archetype: ○"),
            # The commonest misreads left in the Chaos recording once the labels were out of it.
            ("a card's own Epiphanies do not make its stub ambiguous", "Shard:Lig", "Shard:Light"),
            ("the letter the reader cut at may be wrong", "Barrier Der", "Barrier Deployment"),
            ("a name cut at the front is repaired", "lusion of Golden Daffodils", "Illusion of Golden Daffodils"),
            ("a label misread finds no card inside it", "XAttacl", "XAttacl"),
            # Live, in a crowded Rossweisse hand. It fits her Sword Slash and Yuki's Longsword Slash, and only one of them was in the party.
            ("the party settles a stub two combatants' cards fit", "ord Slas", "Sword Slash", "Rossweisse"),
            ("a party that owns neither fit leaves it alone", "ord Slas", "ord Slas", "Haru"),
        ):
            with self.subTest(description):
                self.assertEqual(cards.canonical(reading, frozenset(party)), expected)

    def test_an_archetype_on_offer_is_told_apart_by_its_text(self):
        # Live, on Archetype Resonance's pick none of the three names kept the right glyph, but each effect text read.
        for reading, description, expected in (
            ("Archetype:", "Heal67%1AP", "Archetype: ○"),
            ("Archetype: ∆", "67% ShieldIncrease Damageof next Attack Card byAmount of the first Hit30%(max 300%)", "Archetype: △"),
            ("Archetype: l", "Draw 1 Archetype cardHeal67%", "Archetype: □"),
            ("Slash", "100% Damage", "Slash"),
        ):
            with self.subTest(reading):
                self.assertEqual(expected, cards.described(reading, description))

    def test_the_deck_settles_a_reading_too_garbled_for_the_roster(self):
        # Live, Annihilation came back as "DarkMistSecretAil", 12 letters short, beside Black Dance in the same deck.
        deck = frozenset({"Dark Mist Secret Art: Annihilation", "Dark Mist Secret Art: Black Dance"})
        for description, reading, held, expected in (
            ("the one deck card it fits", "DarkMistSecretAil", deck, "Dark Mist Secret Art: Annihilation"),
            ("no deck read yet leaves it alone", "DarkMistSecretAil", frozenset(), "DarkMistSecretAil"),
            ("two deck cards it fits leave it alone", "DarkMistSecretA", deck, "DarkMistSecretA"),
            ("too little of the name left leaves it alone", "DarkMistS", frozenset({"Dark Mist Secret Art: Annihilation"}), "DarkMistS"),
            ("the deck card a cut reading sits inside", "sidual Herb", frozenset({"Harmonization: Residual Herb"}), "Harmonization: Residual Herb"),
            ("a whole name keeps its own card", "Residual Herb", frozenset({"Harmonization: Residual Herb"}), "Residual Herb"),
            # Live, Joker read as all three, too short for the roster to guess at.
            ("a short name one letter off its deck card", "lokel", frozenset({"Joker", "Cards"}), "Joker"),
            ("a short name with its J read as l", "loker", frozenset(), "Joker"),
            ("a short name one letter off no deck card", "lokel", frozenset({"Cards"}), "lokel"),
        ):
            with self.subTest(description):
                self.assertEqual(cards.canonical(reading, deck=held), expected)

    def test_a_card_the_data_never_heard_of_is_still_played(self):
        chosen = cards.plan(hand("Some Card From A Later Patch"), cards.Board())
        self.assertEqual(len(chosen), 1)

    def test_an_unreadable_card_does_not_stop_the_rest_of_the_turn(self):
        chosen = cards.plan(hand("", JUSTICE_ATTACK), cards.Board())
        self.assertIn(JUSTICE_ATTACK, played(chosen))


class TestKits(unittest.TestCase):
    """Playstyles the generic value per point cannot see."""

    def plays(self, cases):
        """Check that each hand plans to exactly the cards expected, in the order expected.

        Args:
            cases: `(description, cards_in_hand, board, expected)` rows, where `expected` is the planned card names in play order.
        """
        for description, cards_in_hand, board, expected in cases:
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_rossweisse_keeps_her_shards_for_the_fusion(self):
        """Rossweisse's Shards fire while held and fuse into a free Flicker Blade once they are the only cards left."""
        for description, cards_in_hand, expected in (
            # Generic play buys the Shard's 80% hit with the two points the Slash leaves.
            ("a Shard is not bought while the middle holds a card", ("Shard:Light", "Sword Slash", "Shard:Dark"), ["Sword Slash"]),
            # Value per point buys Blade of the Cycle and Charge Launcher, two cards. Clearing the middle wants three.
            ("the middle is cleared before value per point",
             ("Shard:Light", "Charge Launcher", "Sword Slash", "Standing Blade", "Blade of the Cycle", "Shard:Dark"),
             ["Sword Slash", "Standing Blade", "Blade of the Cycle"]),
            ("an upgraded Shard is still a Shard", ("Shard:Light (Cycle)", "Sword Slash", "Shard:Dark (Cycle)"), ["Sword Slash"]),
            # Both read this way in the Chaos recordings.
            ("a misread Shard is still a Shard", ("Shard:l", "Sword Slash", "nard:Dark"), ["Sword Slash"]),
            ("a Shard left alone is played", ("Shard:Dark",), ["Shard:Dark"]),
            # Generic play lists the unplayable Tassel as a free Skill and presses it first.
            ("a Sword Tassel is never played", ("Shard:Light", "Sword Tassel", "Sword Slash", "Shard:Dark"), ["Sword Slash"]),
        ):
            with self.subTest(description):
                self.assertCountEqual(played(cards.plan(hand(*cards_in_hand), cards.Board())), expected)
        with self.subTest("a Shard is kept while the counter says OCR missed the cards beside it"):
            # Live, a hand of 6 read as Shard:Light alone, and the Shard was played with four cards still between.
            self.assertEqual(played(cards.plan(hand("Shard:Light"), cards.Board(hand_size=6))), [])

    def test_a_shard_ocr_missed_is_never_pressed_blind(self):
        # Unread, the far end is a key the picker tries blind for a card it could not read, and it holds Shard:Dark.
        read = kits.reading([{"name": "Shard:Light", "key": "1"}, {"name": "Sword Slash", "key": "3"}], 6)
        self.assertEqual([(card["name"], card["key"]) for card in read], [("Shard:Light", "1"), ("Sword Slash", "3"), ("Shard:Dark", "6")])

    def test_luke_fires_his_bullets_before_cashing_them_in(self):
        """Finisher Round unlocks after five Handgun Bullets this turn, and Dance of the Demon gains a hit per Bullet fired."""
        five_fired = ("Magnum Shot", "Magnum Shot", "Silver Shot", "Uranium Shot", "Tracer Shot")
        self.plays((
            # Generic play tries the free 500% card first, and the game refuses it every turn.
            ("Finisher Round waits for five bullets", ("Finisher Round", "Magnum Shot", "Single Shot"), cards.Board(),
             ["Magnum Shot", "Single Shot"]),
            ("Finisher Round plays once five bullets fired", ("Single Shot", "Finisher Round"), cards.Board(played=five_fired),
             ["Finisher Round", "Single Shot"]),
            # Generic play fires the free bullet first, before Seize buffs it and before Stealth Reload adds more.
            ("the makers and Seize go before the bullets", ("Magnum Shot", "Seize the Opportunity", "Stealth Reload"), cards.Board(),
             ["Stealth Reload", "Seize the Opportunity", "Magnum Shot"]),
            ("Dance waits for every bullet and attack", ("Dance of the Demon", "Magnum Shot", "Silver Shot", "Single Shot"),
             cards.Board(action_points=2), ["Magnum Shot", "Silver Shot", "Single Shot", "Dance of the Demon"]),
            # Its 50% looks worse than Single Shot's 100% until the hits from fired bullets are counted.
            ("Dance is bought over a Single Shot once bullets fired", ("Single Shot", "Dance of the Demon"),
             cards.Board(action_points=1, played=five_fired[:3]), ["Dance of the Demon"]),
        ))

    def test_hugo_builds_stacks_before_spending_them(self):
        """Commence the Hunt stacks come from skills and Dingo Howling and Fan of Daggers, and attacks spend them."""
        self.plays((
            # Generic play puts the shield skill after the attacks that spend its two stacks.
            ("Dingo Howling goes before the attacks", ("Knife Toss", "Dingo Howling"), cards.Board(), ["Dingo Howling", "Knife Toss"]),
            # Generic play buys Knife Toss's 100% ahead of Fan's 60% x3, and plays it first.
            ("Fan of Daggers leads the attacks", ("Knife Toss", "Fan of Daggers"), cards.Board(), ["Fan of Daggers", "Knife Toss"]),
            # Generic play draws first, before any stack is up for the draw to need.
            ("Quick Fix waits for a stack", ("Quick Fix", "Dingo Howling"), cards.Board(), ["Dingo Howling", "Quick Fix"]),
            ("Quick Fix draws first once a stack is up", ("Dingo Howling", "Quick Fix"), cards.Board(last_turn=("Dingo Howling",)),
             ["Quick Fix", "Dingo Howling"]),
            # Owen's shield feeds Hunting Instincts a stack, so it goes before the attack rather than after.
            ("another combatant's skill goes before the attacks", ("Knife Toss", "Weapon Block"), cards.Board(action_points=2),
             ["Weapon Block", "Knife Toss"]),
        ))

    def test_owen_lands_wind_charge_on_an_attack(self):
        """Wind Charge adds a hit to Owen's next attack, and Wind Riding fetches it back from the discard pile."""
        self.plays((
            # Live, it was held with a point to spare, though its hit waits for Owen's next attack on a later turn.
            ("Wind Charge banks its hit with no Owen attack in hand", ("Wind Charge", "Weapon Block"), cards.Board(), ["Wind Charge", "Weapon Block"]),
            ("Break Armor goes first, so it does not take the hit", ("Wind Charge", "Break Armor"), cards.Board(), ["Break Armor", "Wind Charge"]),
            ("Wind Charge lands between Break Armor and the attack", ("Wind Charge", "Gale Strike", "Break Armor"),
             cards.Board(action_points=4), ["Break Armor", "Wind Charge", "Gale Strike"]),
            # Generic play buys the 100% attack over a shield worth 90.
            ("Wind Riding is bought to fetch last turn's Wind Charge", ("Downward Cut", "Wind Riding"),
             cards.Board(action_points=1, last_turn=("Wind Charge",)), ["Wind Riding"]),
        ))

    def test_lucas_plays_sss_before_the_bullets(self):
        """S.S.S buffs the Launcher Bullets played after it for the turn."""
        self.plays((
            # Generic play ranks it as a plain 100% attack, below the 210 bullet, so it lands after it.
            ("S.S.S goes before the bullets it buffs", ("Flame Shot", "S.S.S"), cards.Board(action_points=2), ["S.S.S", "Flame Shot"]),
            # Generic play keeps hand order between the two 100% attacks.
            ("S.S.S goes before a plain attack", ("Machine Gun", "S.S.S"), cards.Board(action_points=2), ["S.S.S", "Machine Gun"]),
        ))

    def test_sereniel_builds_afterglow_before_cashing_it_in(self):
        """Shining Core makes the lasers, and Cobalt Light and Pale Shooting Star only pay once lasers have fired."""
        two_fired = ("Homing Laser", "Homing Laser L")
        self.plays((
            # Generic play leaves the laser maker as filler behind the attack.
            ("Shining Core goes before the attacks", ("Pulse Fire", "Shining Core"), cards.Board(action_points=2), ["Shining Core", "Pulse Fire"]),
            # Generic play buys Cobalt Light's 560 first, with no laser played to build the Afterglow it Ravages on.
            ("Cobalt Light waits for lasers", ("Cobalt Light", "Homing Laser", "Pulse Fire"), cards.Board(), ["Homing Laser", "Pulse Fire"]),
            # Generic play ties the two attacks and keeps hand order.
            ("Cobalt Light goes last", ("Cobalt Light", "Plasma Missile"), cards.Board(action_points=4, played=two_fired),
             ["Plasma Missile", "Cobalt Light"]),
            ("Pale Shooting Star waits for a laser", ("Pale Shooting Star", "Homing Laser", "Pulse Fire"), cards.Board(),
             ["Homing Laser", "Pulse Fire"]),
            # Pins the hold being released, which generic play passes too.
            ("Pale Shooting Star plays once a laser fired", ("Pale Shooting Star", "Pulse Fire"), cards.Board(played=("Homing Laser",)),
             ["Pulse Fire", "Pale Shooting Star"]),
        ))

    def test_magna_plays_her_lead_cards_first(self):
        """Ice Fragment and Storm of Bitter Cold lose their Lead discount once another card has been played."""
        self.plays((
            # Generic play spends a Mental Breakdown card first, the only card it puts ahead of an Upgrade.
            ("Ice Fragment goes before a breakdown card", ("Charm", "Ice Fragment"), cards.Board(action_points=1), ["Ice Fragment", "Charm"]),
            ("Storm of Bitter Cold goes before a breakdown card", ("Charm", "Storm of Bitter Cold"), cards.Board(action_points=1),
             ["Storm of Bitter Cold", "Charm"]),
            # Pins the release: the discount is gone once a card is played, so the breakdown card keeps its usual place.
            ("Ice Fragment keeps its place once a card is played", ("Ice Fragment", "Charm"),
             cards.Board(action_points=1, played=(JUSTICE_ATTACK,)), ["Charm", "Ice Fragment"]),
        ))

    def test_tenebria_plays_rhythms_before_the_cards_that_feed_on_them(self):
        """Call & Response is a Rhythm while held, Encore procs only a Rhythm played just before it, and Spotlight returns a played one."""
        self.plays((
            # Generic play spends Call & Response first, which takes it out of hand and its +30% off every Rhythm.
            ("Call & Response stays in hand beside a Rhythm", ("Call & Response", "Rhythm"), cards.Board(), ["Rhythm"]),
            # Generic play spends Spotlight before the Rhythm it is meant to return.
            ("Spotlight waits for a Rhythm to be played", ("Spotlight", "Rhythm"), cards.Board(), ["Rhythm"]),
            # Generic play plays Encore cold, ahead of the Rhythm it would proc.
            ("Encore waits for a Rhythm", ("Encore", "Rhythm"), cards.Board(), ["Rhythm"]),
            ("Encore follows the Rhythm at once", ("Spotlight", "Encore"), cards.Board(played=("Rhythm",)), ["Encore", "Spotlight"]),
            ("Encore waits when a Rhythm was not the last card", ("Encore", "Rhythm"), cards.Board(played=("Rhythm", "Sound Check")),
             ["Rhythm"]),
            ("Encore waits for the Rhythm Spotlight fetches", ("Encore", "Spotlight"), cards.Board(), ["Spotlight"]),
            # Live, Encore sat in hand with points to spend after Fear, with no Rhythm left to wait for.
            ("Encore plays once no Rhythm can come", ("Encore",), cards.Board(played=("Rhythm", "Fear")), ["Encore"]),
            # Pins the hold being released, which generic play passes too.
            ("Spotlight plays once a Rhythm has been", ("Spotlight", "Rhythm"), cards.Board(played=("Rhythm: Arpeggio",)),
             ["Spotlight", "Rhythm"]),
        ))

    def test_maribell_fires_shelter_strike_after_her_shields(self):
        """Shelter Strike deals Fixed Damage equal to the Shield she owns."""
        self.plays((
            # Generic play buys the 100% Strike over the shield worth 60.
            ("Strike waits for a shield in hand", ("Shelter Strike", "Shelter Defense"), cards.Board(action_points=1), ["Shelter Defense"]),
            # Generic play puts the attack ahead of the skill.
            ("Strike goes after the skill that built the Shield", ("Shelter Strike", "Oh... I see."),
             cards.Board(action_points=2, played=("Shelter Defense",)), ["Oh... I see.", "Shelter Strike"]),
            # Generic play buys Resolute Blitz's 140 over the Strike's 100.
            ("Strike is bought over Blitz once a shield is up", ("Resolute Blitz", "Shelter Strike"),
             cards.Board(action_points=1, played=("Shelter Defense",)), ["Shelter Strike"]),
            # Pins the release: with no shield left in hand the Strike is played.
            ("a lone Strike is played", ("Shelter Strike",), cards.Board(action_points=1), ["Shelter Strike"]),
        ))

    def test_tiphera_copies_archetypes_and_draws_only_after_a_seed(self):
        """Dual Creation copies the Archetypes a Quantum Seed creates, and Form Convergence draws Archetypes only a Seed has made."""
        self.plays((
            # Generic play makes the Archetypes first, so Dual Creation copies none of that pair.
            ("Dual Creation goes before the Seed", ("Quantum Seed", "Dual Creation"), cards.Board(), ["Dual Creation", "Quantum Seed"]),
            # Generic play buys Form Convergence's 200 first, with no Archetype made for it to draw.
            ("Form Convergence waits for a Seed", ("Form Convergence", "Dual Creation"), cards.Board(), ["Dual Creation"]),
            ("the square Archetype waits for a Seed", ("Archetype: \u25a1", "Quantum Seed"), cards.Board(), ["Quantum Seed"]),
            # The Archetypes a Seed makes stay in the deck all battle, so one played two turns back still releases the hold.
            ("Form Convergence plays once this battle's Seed made Archetypes", ("Form Convergence",),
             cards.Board(battle=("Quantum Seed", "Strike")), ["Form Convergence"]),
            # Live, Tiphera's 100% Matter Disintegration took the last point, tied with Nine's 100% Slash on hand order.
            ("a Healer's attack leaves the point to a Core's", ("Matter Disintegration", "Slash"), cards.Board(action_points=1), ["Slash"]),
            ("a Protector's attack leaves the point to a Core's", ("Frozen Fist", "Slash"), cards.Board(action_points=1), ["Slash"]),
            # A heal is a Healer's specialty, and read nothing it tied with Slash on hand order.
            ("a Healer's heal takes the point from a Core's attack", ("Slash", "Barrier Deployment"), cards.Board(action_points=1, health=0.5),
             ["Barrier Deployment"]),
            ("a heal leaves the point to an attack while the team is healthy", ("Slash", "Barrier Deployment"),
             cards.Board(action_points=1, health=cards.HEALTHY), ["Slash"]),
        ))

    def test_mei_lin_buffs_first_and_ends_on_the_spire(self):
        """Rising Dragon Spire gains hits from the cards before it, and Spirit of the Aromata buffs the cards after it."""
        self.plays((
            # Generic play keeps hand order among the attacks.
            ("the Spire follows the Strikes", ("Rising Dragon Spire", "Strike", "Strike"), cards.Board(action_points=3),
             ["Strike", "Strike", "Rising Dragon Spire"]),
            # Generic play puts the buff after the attacks it was meant to raise.
            ("Spirit goes before the attacks", ("Strike", "Spirit of the Aromata"), cards.Board(action_points=2),
             ["Spirit of the Aromata", "Strike"]),
            # Generic play buys Sovereignty's 300% for the two points, ahead of two Strikes.
            ("Sovereignty does not take the points from the Strikes", ("Flame Dragon's Sovereignty", "Strike", "Strike"),
             cards.Board(action_points=2), ["Strike", "Strike"]),
        ))

    def test_tressa_curses_first_and_makes_daggers_before_throwing(self):
        """Curse counts only Attacks played after it, and Unsheathe Dagger and Shadow Reload make the daggers the turn is spent on."""
        self.plays((
            # Generic play ranks Curse at a flat 100, below a free 120% attack, and so plays the attack first.
            ("Curse goes before a free attack", ("Homing Laser", "Curse"), cards.Board(), ["Curse", "Homing Laser"]),
            # Generic play throws first, and the dagger maker waits behind it as filler.
            ("Unsheathe Dagger goes before Dagger Throw", ("Dagger Throw", "Unsheathe Dagger"), cards.Board(action_points=2),
             ["Unsheathe Dagger", "Dagger Throw"]),
            ("Shadow Reload goes before Dagger Throw", ("Dagger Throw", "Shadow Reload"), cards.Board(action_points=2),
             ["Shadow Reload", "Dagger Throw"]),
            # Generic play ties them and keeps hand order, which spends the Retain card before the plain attack.
            ("Advanced Shadow Dagger goes after Dagger Throw", ("Advanced Shadow Dagger", "Dagger Throw"), cards.Board(),
             ["Dagger Throw", "Advanced Shadow Dagger"]),
        ))

    def test_mika_spends_points_on_the_partner_first(self):
        """Water Arrow, Water Barrier and Whirlpool are cut from her deck by the guides, so a partner's card is bought first."""
        self.plays((
            # Generic play ties Water Arrow with the partner's 100% attack and takes the one that comes first in hand.
            ("a partner attack beats Water Arrow", ("Water Arrow", JUSTICE_ATTACK), cards.Board(action_points=1), [JUSTICE_ATTACK]),
            ("a partner attack beats Water Barrier", ("Water Barrier", JUSTICE_ATTACK), cards.Board(action_points=1), [JUSTICE_ATTACK]),
            # Generic play ties Whirlpool's 100 per point with the attacks and takes it first.
            ("two partner attacks beat Whirlpool", ("Whirlpool", JUSTICE_ATTACK, JUSTICE_ATTACK), cards.Board(action_points=2),
             [JUSTICE_ATTACK, JUSTICE_ATTACK]),
        ))

    def test_veronica_leaves_the_ballistas_and_sets_up_reload_first(self):
        """Her Ballistas fire themselves at the end of the turn, and Firing Preparation, Bombardment Prep and Pendant feed them."""
        self.plays((
            # Generic play clicks the Ballista first, as a free Attack.
            ("a Ballista is not played", ("Ballista", "Repose"), cards.Board(), ["Repose"]),
            ("a Ballista alone ends the turn", ("Piercing Ballista",), cards.Board(), []),
            # Generic play ties the power cards and keeps the buying order, which puts Repose's 260 first.
            ("Firing Preparation goes first", ("Repose", "Firing Preparation"), cards.Board(), ["Firing Preparation", "Repose"]),
            ("Bombardment Prep goes before Pendant of Resolution", ("Pendant of Resolution", "Bombardment Prep"), cards.Board(),
             ["Bombardment Prep", "Pendant of Resolution"]),
            ("Pendant of Resolution goes before the skills", ("Repose", "Pendant of Resolution"), cards.Board(),
             ["Pendant of Resolution", "Repose"]),
        ))

    def test_narja_sets_up_before_the_attacks(self):
        """Voluntary Control makes Voracity and Domain of Voracity raises Tenacity damage, and both only help the attacks after them."""
        self.plays((
            # Generic play runs the skill after every attack.
            ("Voluntary Control goes before the attacks", (JUSTICE_ATTACK, "Voluntary Control"), cards.Board(action_points=2),
             ["Voluntary Control", JUSTICE_ATTACK]),
            # Generic play keeps hand order among the attacks.
            ("Domain of Voracity goes before the attacks", (JUSTICE_ATTACK, "Domain of Voracity"), cards.Board(action_points=2),
             ["Domain of Voracity", JUSTICE_ATTACK]),
            ("Voluntary Control goes before Domain", ("Domain of Voracity", "Voluntary Control"), cards.Board(action_points=2),
             ["Voluntary Control", "Domain of Voracity"]),
            # Generic play ties it with a real attack and takes the one first in hand.
            ("Attack Response gives way to a real attack", ("NA: Attack Response", JUSTICE_ATTACK), cards.Board(action_points=1), [JUSTICE_ATTACK]),
        ))

    def test_yuki_enables_inspiration_before_the_attacks_and_ends_on_iceberg(self):
        """Trickery Strike enables Inspiration on the attacks played after it, and Iceberg Cleave is the payoff after the buffs."""
        self.plays((
            # Generic play ties Trickery Strike with the other 180 attack and keeps hand order.
            ("Trickery Strike goes before the attacks", ("Iceberg Cleave", "Trickery Strike"), cards.Board(), ["Trickery Strike", "Iceberg Cleave"]),
            # Generic play buys Iceberg Cleave's 180 per point first and plays it first.
            ("Iceberg Cleave goes after Flash Slash", ("Iceberg Cleave", "Flash Slash"), cards.Board(), ["Flash Slash", "Iceberg Cleave"]),
        ))

    def test_nia_orders_her_cycling_cards(self):
        """Adagio leaves a discard on top for G Chord, Soul Riff counts later discards, and Mute Accent discards the dearest card."""
        self.plays((
            # Generic play puts the skill after the attack.
            ("G Chord goes before the attacks", (JUSTICE_ATTACK, "G Chord"), cards.Board(action_points=2), ["G Chord", JUSTICE_ATTACK]),
            # Generic play runs the free discarder first, so Soul Riff counts none of it.
            ("Soul Riff goes before Adagio", (FREE_DRAW, "Soul Riff"), cards.Board(action_points=1), ["Soul Riff", FREE_DRAW]),
            ("Curiosity goes before the attacks", (JUSTICE_ATTACK, "Nia\u2019s Curiosity"), cards.Board(action_points=2),
             ["Nia\u2019s Curiosity", JUSTICE_ATTACK]),
            # Generic play throws the 2 AP card away along with its own 220%.
            ("Mute Accent waits while a dearer card is in hand", ("Mute Accent", BIG_ATTACK), cards.Board(action_points=3), [BIG_ATTACK]),
        ))

    def test_adelheid_sets_up_and_waits_for_a_pack(self):
        """Once Upon A Time blesses before Protect Us draws, Garden of Secrets is a top spend, and Doggie (Pack) comes in twos."""
        self.plays((
            # Generic play keeps hand order, so Protect Us draws Blessing cards before any exist.
            ("Once Upon A Time goes before Protect Us", ("Protect Us", "Once Upon A Time"), cards.Board(), ["Once Upon A Time", "Protect Us"]),
            # Generic play rates Garden's 200% shield at 120 and buys the 200% attack ahead of it.
            ("Garden of Secrets ties her best attack", ("Garden of Secrets", "Truth Behind A Story"), cards.Board(action_points=1),
             ["Garden of Secrets"]),
            # Generic play plays the free Doggie at once.
            ("a lone Doggie (Pack) waits", ("Doggie (Pack)", "Gather Around"), cards.Board(), ["Gather Around"]),
            # Pins the hold being released, so it passes without the kit too.
            ("two Doggie (Pack) are played", ("Doggie (Pack)", "Doggie (Pack)"), cards.Board(), ["Doggie (Pack)", "Doggie (Pack)"]),
        ))

    def test_amir_builds_metalization_and_ends_on_iron_skin(self):
        """Hovering Metal and Metal Extraction give Metalization first, Iron Skin ends the turn, and Steel Barrier sets off a hit after Hurricane."""
        self.plays((
            # Generic play puts the generators in the late skill phase, after the attack that would spend their stacks.
            ("the generators go before the attacks", ("Rapier", "Hovering Metal"), cards.Board(action_points=2), ["Hovering Metal", "Rapier"]),
            # Generic play keeps hand order among the late skills, so the Finale ends the turn on top of the shield.
            ("Iron Skin goes after every other card", ("Iron Skin", "Steel Barrier"), cards.Board(action_points=2), ["Steel Barrier", "Iron Skin"]),
            # Generic play rates its 100% shield below Rapier's 100% hit.
            ("Steel Barrier beats Rapier once Hurricane is played", ("Rapier", "Steel Barrier"),
             cards.Board(action_points=1, played=("Full Metal Hurricane",)), ["Steel Barrier"]),
        ))

    def test_anika_discounts_one_big_attack_and_ends_on_reloading(self):
        """Warming Up waits for a two-cost attack and plays just before it, Rampage Trigger lands four hits last, and Reloading ends the turn."""
        self.plays((
            # Generic play spends the free Finale first and throws the hand away.
            ("Reloading goes last", ("Reloading", "Shock Gun"), cards.Board(action_points=1), ["Shock Gun", "Reloading"]),
            # Generic play discounts a card that costs one anyway.
            ("Warming Up waits for a big attack", ("Warming Up", "Shock Gun"), cards.Board(action_points=2), ["Shock Gun"]),
            # Generic play prices its 100% line at a single hit, so Shock Gun and Blaster Swing take the points.
            ("Rampage Trigger is bought for its four hits", ("Rampage Trigger", "Blaster Swing", "Shock Gun"), cards.Board(),
             ["Shock Gun", "Rampage Trigger"]),
        ))
        # With only Rampage Trigger to discount, generic play still puts Warming Up ahead of Shock Gun and wastes the discount on it.
        board = cards.Board(hand=("Warming Up", "Shock Gun", "Rampage Trigger"))
        self.assertGreater(cards.phase("Warming Up", board), cards.phase("Shock Gun", board))

    def test_arabella_applies_fracture_before_it_detonates(self):
        """Scream For Me and Hollow Verdict apply Fracture, Sadistic Restraint detonates it, and The Art of Unmaking waits for it."""
        self.plays((
            # Generic play orders the three by hand order, so Sadistic Restraint detonates Fracture that is not there yet.
            ("apply, then detonate", ("Sadistic Restraint", "Hollow Verdict", "Scream For Me"), cards.Board(),
             ["Scream For Me", "Hollow Verdict", "Sadistic Restraint"]),
            # Generic play opens with the 200% card, which has no harmful effect to grow on.
            ("The Art of Unmaking waits for an applier", ("The Art of Unmaking", "Scream For Me"), cards.Board(action_points=2), ["Scream For Me"]),
            # Pins the hold being released once a Fracture card has been played, so it passes without the kit too.
            ("The Art of Unmaking plays after an applier", ("The Art of Unmaking", "Sadistic Restraint"),
             cards.Board(action_points=2, played=("Scream For Me",)), ["The Art of Unmaking", "Sadistic Restraint"]),
            # Generic play buys the 60% Diagonal Slash ahead of the 40% appliers.
            ("filler yields to the Fracture cards", ("Diagonal Slash", "Scream For Me", "Hollow Verdict"), cards.Board(action_points=2),
             ["Scream For Me", "Hollow Verdict"]),
        ))

    def test_beryl_lets_charged_shot_grow_in_hand(self):
        """Charged Shot only takes points nothing else wants, a kept Opening Found takes the points, and the Specialist goes before the attacks."""
        self.plays((
            # Generic play spends two points on the 270% Charged Shot at once, leaving one for a single attack.
            ("cheaper attacks take the points", ("Charged Shot", "Launcher", "Opening Found"), cards.Board(), ["Opening Found", "Launcher"]),
            # Pins the hold being released when the points would otherwise go unused, so it passes without the kit too.
            ("spare points go to Charged Shot", ("Charged Shot",), cards.Board(), ["Charged Shot"]),
            # Generic play files the Specialist with the late skills, after the attack.
            ("the Specialist goes before the attacks", ("Launcher", "Heavy Weapons Specialist"), cards.Board(action_points=2),
             ["Heavy Weapons Specialist", "Launcher"]),
            # Generic play buys the 210% Armor-Piercing Rounds over a 160% Opening Found that has an extra hit for this turn.
            ("a kept Opening Found takes the point", ("Armor-Piercing Rounds", "Opening Found"),
             cards.Board(action_points=1, kept=("Opening Found",)), ["Opening Found"]),
            ("a Charged Shot that does not grow is spent", ("Charged Shot", "Launcher", "Opening Found"), cards.Board(deck={"Charged Shot": FLAT_CHARGED_SHOT}),
             ["Opening Found", "Charged Shot"]),
            ("a kept Opening Found without the extra hit is not doubled", ("Armor-Piercing Rounds", "Opening Found"),
             cards.Board(action_points=1, kept=("Opening Found",), deck={"Opening Found": FREE_OPENING_FOUND}), ["Armor-Piercing Rounds"]),
        ))

    def test_cassius_keeps_to_his_deck_cards(self):
        """Wild Card, Cards and Mana Field are filler, Triple 0 follows the attacks it counts, and Shuffle is a rescue."""
        self.plays((
            # Generic play buys the 220% Wild Card for two points and has none left for Pop Eyed Popper.
            ("filler yields to Joker and the Popper", ("Wild Card", "Joker", "Pop Eyed Popper"), cards.Board(), ["Pop Eyed Popper", "Joker"]),
            # Generic play plays the free Quest card first, before any attack has been counted.
            ("Triple 0 follows the attacks", ("Triple 0", "Dice Trick"), cards.Board(action_points=2), ["Dice Trick", "Triple 0"]),
            # Generic play shuffles the hand away after the draw.
            ("Shuffle waits while a card can be played", ("Shuffle", "Devil Dice"), cards.Board(), ["Devil Dice"]),
            # Pins the hold being released when nothing else is playable, so it passes without the kit too.
            ("Shuffle rescues a dead hand", ("Shuffle", CURSE), cards.Board(), ["Shuffle"]),
        ))

    def test_chizuru_spends_her_buffs_on_one_shadow(self):
        """Shadow of the Moon waits for Oni Hunt and Tsukuyomi and plays last, Karmic Flames leads, and Tsukuyomi sits right before Oni Hunt."""
        self.plays((
            # Generic play spends Shadow of the Moon at once, with the Oni Hunt buff still unplayed.
            ("Shadow waits for the buffs", ("Shadow of the Moon", "Oni Hunt"), cards.Board(action_points=2), ["Oni Hunt"]),
            # Generic play keeps hand order among the attacks, so Shadow goes first.
            ("Shadow goes last", ("Shadow of the Moon", "Moonslash"), cards.Board(action_points=2), ["Moonslash", "Shadow of the Moon"]),
            # Generic play keeps hand order, so the curse lands after the other hit.
            ("Karmic Flames leads the attacks", ("Moonslash", "Karmic Flames"), cards.Board(action_points=2), ["Karmic Flames", "Moonslash"]),
            # Generic play plays the free Tsukuyomi ahead of every setup card, and so well before Oni Hunt.
            ("Tsukuyomi sits right before Oni Hunt", ("Tsukuyomi", BUFF, "Oni Hunt"), cards.Board(action_points=2), [BUFF, "Tsukuyomi", "Oni Hunt"]),
        ))

    def test_diana_discards_her_quietus_attacks(self):
        """Quietus cards fire free when discarded, so Diana keeps them for Blooming Love and Heart Breaker rather than paying for them."""
        milk = "C\u2019mere, Milk & Pong!"
        self.plays((
            # Generic play pays a point for each attack as a plain hit.
            ("the attacks are held while Blooming Love can discard them", ("With All My Heart!", "Pistol of Purification", "Blooming Love"),
             cards.Board(), ["Blooming Love"]),
            ("the attacks are held while Heart Breaker can discard them", ("Pistol of Purification", "Heart Breaker"), cards.Board(),
             ["Heart Breaker"]),
            ("Cupid Shot is held for a discard too", ("Cupid Shot", "Blooming Love"), cards.Board(), ["Blooming Love"]),
            # Generic play makes the Shakers last of all.
            ("Milk & Pong makes Shakers before the rest", ("Protect Me", milk), cards.Board(action_points=2), [milk, "Protect Me"]),
            # Generic play fires the 500% card at once, with no bullet types in hand to count.
            ("Liberated Feelings waits for both bullet types", ("Liberated Feelings", "Heart Shaker", "Disruption Fire"), cards.Board(),
             ["Heart Shaker", "Disruption Fire"]),
            # Generic play plays the free bullets first, which empties the hand it counts.
            ("Liberated Feelings counts the bullets before they are played", ("Heart Shaker", "Heart Breaker", "Liberated Feelings"),
             cards.Board(), ["Liberated Feelings", "Heart Shaker", "Heart Breaker"]),
        ))

    def test_fei_sets_up_before_drawing_and_cashing_in(self):
        """Formation must precede the draws, Blazing War Dance follows the Descent they gain, and Soulfire Dance wants the points left."""
        formation = "Exorcist\u2019s Formation"
        self.plays((
            # Generic play draws first, and Soliloquy discards the Formation it draws.
            ("Formation goes before the draws", ("Soliloquy", formation), cards.Board(), [formation, "Soliloquy"]),
            # Generic play fires the free War Dance at the start of the turn, with no Descent gained.
            ("Blazing War Dance goes after the attacks", ("Blazing War Dance", "Azure Flame"), cards.Board(), ["Azure Flame", "Blazing War Dance"]),
            # Generic play spends the points on the small cards, so Soulfire Dance is left with none.
            ("small cards are held for Soulfire Dance", ("Azure Flame", "Soulfire Dance", "Melancholy"), cards.Board(), ["Soulfire Dance"]),
        ))

    def test_haru_keeps_her_buffs_for_the_shot(self):
        """Anchor Pointer fetches an Anchor Shot only when none is in hand, and the buffs only work on a card in hand."""
        self.plays((
            # Generic play fetches the Shot while one is already in hand.
            ("Pointer waits while a Shot is in hand", ("Anchor Pointer", "Anchor Shot"), cards.Board(), ["Anchor Shot"]),
            # Generic play spends the buff with no Shot in hand to take it.
            ("Lift Anchor waits for a Shot", ("Lift Anchor", "Anchor"), cards.Board(action_points=1), ["Anchor"]),
            ("Charge Energy waits for an attack", ("Charge Energy", "Anchor Drop"), cards.Board(action_points=1), ["Anchor Drop"]),
            # Pins the hold being released, so it passes with the kit removed.
            ("Pointer fetches a Shot that is not in hand", ("Anchor Pointer", "Anchor Drop"), cards.Board(action_points=1),
             ["Anchor Pointer", "Anchor Drop"]),
        ))

    def test_heidemarie_starts_one_linked_chain_after_the_rest(self):
        """Playing a Linked card discards the other Linked cards in hand, so it comes last, and only one is played."""
        self.plays((
            # Generic play buys the 160% Sword Rain ahead of the Flash and plays it first.
            ("the Linked starter goes after the other attacks", ("Sword Rain", "Sword Flash"), cards.Board(action_points=2),
             ["Sword Flash", "Sword Rain"]),
            # Generic play pays for the second Linked card, which the first one has already discarded.
            ("no second Linked card once one was played", ("Thread of Light", "Sword Flash"), cards.Board(played=("Sword Rain",)),
             ["Sword Flash"]),
            # Generic play sees a free skill and plays it, and it can never be played by hand.
            ("Compression is never played", ("Effulgent Compression", "Sword Flash"), cards.Board(action_points=1), ["Sword Flash"]),
            # Generic play makes the Blades after the attack that should have been the starter.
            ("Expansion makes Blades before the attacks", ("Sword Flash", "Effulgent Expansion"), cards.Board(),
             ["Effulgent Expansion", "Sword Flash"]),
            # Generic play fires the free nuke first, before the chain has put Blades in the graveyard.
            ("Release goes after the chain", ("Effulgent Release", "Sword Flash"), cards.Board(action_points=1),
             ["Sword Flash", "Effulgent Release"]),
            # Live: a hand of Blades and no card of her own deck left the kit off, and the Blade went ahead of Sword Slash.
            ("a hand holding only made cards still runs the kit", ("Effulgent Blade", "Sword Slash"), cards.Board(),
             ["Sword Slash", "Effulgent Blade"]),
        ))

    def test_hilde_fills_the_draw_pile_before_drawing(self):
        """Quiver Reload makes the arrows every draw pulls, and Vortex Arrow gains a hit per attack card drawn before it."""
        self.plays((
            # Generic play draws first, and plays the Quiver with the fillers at the end.
            ("the Quiver goes first and Vortex Arrow last", ("Vortex Arrow", "Quiver Reload", "Draw & Release"), cards.Board(),
             ["Quiver Reload", "Draw & Release", "Vortex Arrow"]),
            # Generic play ties the Quiver with Big Game Ranger and takes whichever sits first in hand.
            ("the Quiver is bought with Big Game Ranger", ("Big Game Ranger", "Quiver Reload", "Vortex Arrow", "Draw & Release"),
             cards.Board(), ["Quiver Reload", "Big Game Ranger", "Vortex Arrow"]),
            # Live, all three points went on attacks at 180-320, and both Upgrades waited for a turn that never had points to spare.
            ("Upgrades are bought before attacks", ("Echo of Futility", "Deluge", "Multishot", "Plasma Rain", "Big Game Ranger"), cards.Board(enemies=3),
             ["Deluge", "Big Game Ranger", "Echo of Futility"]),
            ("Big Game Ranger goes before the draw", ("Draw & Release", "Big Game Ranger"), cards.Board(action_points=2),
             ["Big Game Ranger", "Draw & Release"]),
            ("Plasma Rain goes before the arrows it should debuff", ("Vortex Arrow", "Plasma Rain"), cards.Board(action_points=2),
             ["Plasma Rain", "Vortex Arrow"]),
        ))

    def test_kayron_exhausts_before_the_finishers(self):
        """Black Hole grows with every Futility exhausted, so it waits until the Futility is played."""
        self.plays((
            # Generic play buys Black Hole's 240% over the Futility and plays it first.
            ("Black Hole waits for the Futility", ("Black Hole", "Futility"), cards.Board(), ["Futility"]),
            # Pins the hold being released, so it passes with the kit removed.
            ("Black Hole is played once the Futility is gone", ("Black Hole",), cards.Board(), ["Black Hole"]),
            # Live, both points went on Futility at 160 each. With nothing of Kayron's to feed, the partners' cards come first.
            ("a lone Futility waits for the partners", ("Futility", "Futility", "Futility", "Multishot", "Bowguard"), cards.Board(action_points=2),
             ["Multishot", "Bowguard"]),
            ("Futility still goes first with Brand of Annihilation to feed", ("Futility", "Futility", "Multishot", "Brand of Annihilation"),
             cards.Board(action_points=2), ["Futility", "Futility"]),
            # Live, the last point went on a Futility with Multishot and Plasma Rain still in hand.
            ("the last point goes to a partner's card", ("Brand of Annihilation", "Futility", "Multishot", "Plasma Rain"),
             cards.Board(action_points=1, health=1.0), ["Multishot"]),
        ))

    def test_khalipe_lets_vulture_ejection_fire_free(self):
        """Vulture Ejection fires free when a 2-cost card is played with it in hand, and Aquila costs 2 while it is."""
        self.plays((
            # Generic play pays all three points for the Ejection, ahead of a 2-cost card worth less per point.
            ("the Ejection is held for a 2-cost card", ("Vulture Ejection", "Mutation: Atomic Decomposition"), cards.Board(),
             ["Mutation: Atomic Decomposition"]),
            # Generic play plays the better 2-cost card first, which uses the Ejection up before Aquila can take its bonus.
            ("Aquila goes first while the Ejection is in hand", ("Hew Lv. 3", "Greatsword Aquila", "Vulture Ejection"), cards.Board(),
             ["Greatsword Aquila", "Hew Lv. 3"]),
            # A live run held both: the Ejection waited on a Hew that Nine's kit never played, and on a card the cheap attacks outbid.
            ("the 3-cost Hew is played to fire the Ejection", ("Vulture Ejection", "Slash", "Experienced Strike", "Hew"), cards.Board(), ["Hew"]),
            ("the card that fires the Ejection is bought over cheap attacks",
             ("Vulture Ejection", "Mutation: Forbidden Algorithm", "Slash", "Experienced Strike"), cards.Board(), ["Mutation: Forbidden Algorithm"]),
        ))

    def test_nine_levels_hew_before_firing_it(self):
        """Hew grows a level each time it is exhausted, so Nine holds it until the top level and spends the exhaust cards on it."""
        self.plays((
            # Generic play spends all three points on a Hew that has grown nothing.
            ("a low Hew is held", ("Hew Lv. 1", "Fighting Spirit"), cards.Board(), ["Fighting Spirit"]),
            # A deck with no exhaust card held its Hew all run.
            ("a low Hew is played with nothing to grow it", ("Hew", "Slash"), cards.Board(), ["Hew"]),
            # Generic play buys Experienced Strike's 140% over a skill worth 100.
            ("Fighting Spirit is bought to level Hew", ("Experienced Strike", "Hew Lv. 1", "Fighting Spirit"),
             cards.Board(action_points=1), ["Fighting Spirit"]),
            # Pins the hold being released at the top level.
            ("a full Hew is played", ("Hew Lv. 3",), cards.Board(), ["Hew Lv. 3"]),
            ("Extreme is not full at level 4", ("Hew (Extreme) Lv. 4", "Fighting Spirit"), cards.Board(), ["Fighting Spirit"]),
            # Generic play takes the one-point attack that would exhaust the full Hew.
            ("Fatal Strike waits while Hew is full", ("Fatal Strike", "Hew Lv. 3"), cards.Board(), ["Hew Lv. 3"]),
            ("Fighting Spirit fires a full Hew", ("Hew Lv. 3", "Fighting Spirit"), cards.Board(), ["Fighting Spirit"]),
            # Generic play puts the boost after the Hew it was meant for.
            ("Experienced Strike goes before the Hew", ("Hew Lv. 3", "Experienced Strike"), cards.Board(), ["Experienced Strike", "Hew Lv. 3"]),
            # Generic play spends a point on a skill that has no Hew to fire.
            ("Fighting Spirit has nothing to fire once Hew is gone", ("Fighting Spirit", "Slash"), cards.Board(played=("Hew Lv. 3",)),
             ["Slash"]),
        ))

    def test_olga_stacks_before_she_cashes_in(self):
        """Rift and Desire stack and activate Fracture and Agony, Break Apart returns them, and Reckoning cashes the stacks in."""
        stacker = ("Rift of Severance",)
        self.plays((
            # Generic play fires the free Reckoning first, before any stack exists.
            ("Reckoning waits for a stack", ("Reckoning", "Reaping Slash"), cards.Board(), ["Reaping Slash"]),
            ("Reckoning follows the stacker", ("Reckoning", "Dispersed Desire"), cards.Board(action_points=1), ["Dispersed Desire", "Reckoning"]),
            # Pins the hold being released by last turn's stacker.
            ("Reckoning plays on a stack from last turn", ("Reckoning",), cards.Board(last_turn=stacker), ["Reckoning"]),
            # Generic play buys the plain 100% over an 80% that activates the stacks.
            ("a stacker is bought over Reaping Slash", ("Reaping Slash", "Rift of Severance"), cards.Board(action_points=1),
             ["Rift of Severance"]),
            # Generic play puts the Break Apart skill after every attack, so it fetches nothing back in time.
            ("Break Apart follows the first stacker", ("Dispersed Desire", "Break Apart & Renew"), cards.Board(action_points=2, played=stacker),
             ["Break Apart & Renew", "Dispersed Desire"]),
        ))

    def test_orlea_keeps_cards_that_need_creatures(self):
        """Growing Creature is better kept, Swiftie and Softie grow until the hand is crowded, the creature cards wait for creatures, and Softie
        buffs first."""
        swiftie, softie, sturdie = "Swiftie \u2605\u2605\u2605", "Softie \u2605\u2605\u2605", "Sturdie \u2605"
        crowded = ("Slash",) * 5
        for description, cards_in_hand, expected in (
            # Generic play spends a point to make a one-star creature that waiting would have made a three-star one.
            ("Growing Creature is never played", ("Growing Creature", "Attack, My Minions"), ["Attack, My Minions"]),
            # Generic play spends every free creature on sight, where Auto ends its turns holding Swiftie and Softie.
            ("Swiftie and Softie are kept and Sturdie played", (swiftie, softie, sturdie, "Slash"), [sturdie, "Slash"]),
            ("Will of Light waits for a hand of creatures", ("Will of Light", swiftie, softie), []),
            # Pins the hold being released at three creatures.
            ("Will of Light plays with three creatures", ("Will of Light", swiftie, softie, sturdie), [sturdie, "Will of Light"]),
            ("Growth Acceleration waits for a creature", ("Growth Acceleration", "Healing of Light"), ["Healing of Light"]),
            # Pins the hold being released by a crowded hand, and generic play takes hand order, so the Swiftie attacks before the buff is up.
            ("Softie goes before Swiftie once the hand is crowded", (swiftie, softie, sturdie, *crowded), [softie, swiftie, sturdie, *crowded[:3]]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), cards.Board())), expected)

    def test_rei_buffs_before_the_attacks(self):
        """Strike of Darkness, Dark Condensation and Predator's Blade buff the attacks played after them."""
        for description, cards_in_hand, expected in (
            # Generic play files the 100% buff attack with the plain attacks, in hand order.
            ("Strike of Darkness goes before the basic attack", ("Dark Blade", "Strike of Darkness"), ["Strike of Darkness", "Dark Blade"]),
            # Generic play files this one as a skill, after every attack.
            ("Dark Condensation goes before the attack", ("Dark Blade", "Dark Condensation"), ["Dark Condensation", "Dark Blade"]),
            ("the buffs keep their order", ("Predator's Blade", "Dark Condensation", "Strike of Darkness"),
             ["Strike of Darkness", "Dark Condensation", "Predator's Blade"]),
            # Live, Dark Condensation tied with the other 1-cost skills and lost the buy, though it boosts the attack beside it.
            # Material Regeneration is a Healer's heal, so it is bought over Photo Time's guessed worth.
            ("Dark Condensation is bought for the attack it boosts", ("Photo Time", "Material Regeneration", "Predator's Blade", "Dark Condensation"),
             ["Dark Condensation", "Predator's Blade", "Material Regeneration"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), cards.Board())), expected)

    def test_renoa_keeps_her_bullets_in_hand(self):
        """Dirge Bullets fire when the turn ends, and the payoff attacks scale with the bullets still in hand."""
        bullets = ("Dirge Bullet",) * 5
        self.plays((
            # Generic play spends a point on the bullet, which would have fired for free at turn end.
            ("a bullet is never played", ("Dirge Bullet", "Annihilation Shot"), cards.Board(), ["Annihilation Shot"]),
            # Generic play buys the 300% card on sight, with two bullets for it to count.
            ("Last-Ditch Assault waits for bullets", ("Last-Ditch Assault", "Dirge Bullet", "Dirge Bullet", "Annihilation Shot"), cards.Board(),
             ["Annihilation Shot"]),
            ("Last-Ditch Assault plays with five bullets", ("Last-Ditch Assault", *bullets), cards.Board(), ["Last-Ditch Assault"]),
            # Generic play buys the payoffs by value, Last-Ditch Assault first, so it discards the bullets the others count.
            ("the payoffs go Ballad, Instant Judgment, Last-Ditch", ("Last-Ditch Assault", "Instant Judgment", "Ballad of Pitch Black", *bullets),
             cards.Board(), ["Ballad of Pitch Black", "Instant Judgment", "Last-Ditch Assault"]),
            # Generic play buys the 180% Ballad first, before the bullet Echo of Sorrow makes for it to count.
            ("Echo of Sorrow goes before Ballad", ("Ballad of Pitch Black", "Echo of Sorrow"), cards.Board(action_points=2),
             ["Echo of Sorrow", "Ballad of Pitch Black"]),
        ))

    def test_rin_takes_the_stance_before_attacking(self):
        """Dark Mist Stance buffs her attacks and Inner Art, Black Dance counts Skill cards in hand, and an ally attack ends the stance."""
        self.plays((
            # Generic play buys Drawing Slash's 120% first, so its bonus lands before the stance is up.
            ("Destruction goes before Drawing Slash", ("Drawing Slash", "Dark Mist Secret Art: Destruction"), cards.Board(),
             ["Dark Mist Secret Art: Destruction", "Drawing Slash"]),
            # Generic play files the buff skill after the attacks.
            ("Inner Art goes before the attack", ("Dark Mist Sword: First Form", "Dark Mist Inner Art"), cards.Board(),
             ["Dark Mist Inner Art", "Dark Mist Sword: First Form"]),
            # Generic play buys Black Dance and the Skill cards it counts, and never the First Form that would take the stance for them.
            ("First Form takes the stance for Black Dance",
             ("Sacred Censer", "Growth Acceleration", "Frozen Fist", "Dark Mist Sword: First Form", "Dark Mist Secret Art: Black Dance"),
             cards.Board(action_points=3, deck=RIN_DECK),
             ["Dark Mist Sword: First Form", "Dark Mist Secret Art: Black Dance", "Sacred Censer"]),
            # Without the Epiphany, First Form takes no stance and Black Dance gets no bonus to chase.
            ("a plain First Form is not bought for the stance", ("Sacred Censer", "Growth Acceleration", "Slash", "Dark Mist Sword: First Form",
             "Dark Mist Secret Art: Black Dance"), cards.Board(action_points=3), ["Dark Mist Secret Art: Black Dance", "Slash", "Sacred Censer"]),
            ("the cost cut goes before the cards it cheapens",
             ("Dark Mist Secret Art: Black Dance", "Dark Mist Secret Art: Annihilation", "Dark Mist Sword: First Form"),
             cards.Board(action_points=3, deck=RIN_DECK),
             ["Dark Mist Sword: First Form", "Dark Mist Secret Art: Annihilation", "Dark Mist Secret Art: Black Dance"]),
            # Generic play takes hand order, so the ally's attack ends the stance before Rin's.
            ("an ally's attack goes after Rin's", ("Annihilation Shot", "Dark Mist Sword: First Form"), cards.Board(action_points=2),
             ["Dark Mist Sword: First Form", "Annihilation Shot"]),
        ))

    def test_rita_builds_chronicle_before_time_paradox(self):
        """Time Paradox converts Chronicle that spent AP builds, Time Axis Collapse counts the Cost left in hand, and Future Decreed is a gamble."""
        self.plays((
            # Generic play converts at once, when this turn has built no Chronicle to convert.
            ("Time Paradox waits for other plays", ("Time Paradox", "Anchor", "Time Axis Collapse"), cards.Board(), ["Time Axis Collapse", "Anchor"]),
            # Pins the hold being released once two cards have been played.
            ("Time Paradox plays after two cards", ("Time Paradox", "Anchor"), cards.Board(played=("Time Axis Collapse", "Anchor")),
             ["Time Paradox", "Anchor"]),
            # Generic play leaves the prime card ahead of it, which takes its Cost out of the hand first.
            ("Time Axis Collapse goes before the hand empties", ("Break Armor", "Time Axis Collapse"), cards.Board(),
             ["Time Axis Collapse", "Break Armor"]),
            # Generic play plays it as a skill and gets a random 3-Cost card.
            ("Future Decreed stays in hand", ("Future Decreed", "Anchor"), cards.Board(), ["Anchor"]),
            # Live, Gear Bag and an attack took the battle's points while Chrono Archon sat in hand, and Time Paradox converted nothing.
            ("Chrono Archon takes the point from an attack", ("Slash", "Chrono Archon"), cards.Board(action_points=1), ["Chrono Archon"]),
            ("Time Paradox waits for Chrono Archon", ("Time Paradox", "Chrono Archon"), cards.Board(action_points=1, played=("Slash", "Slash")),
             ["Chrono Archon"]),
            ("a second Chrono Archon is an ordinary card", ("Time Paradox", "Slash", "Chrono Archon"),
             cards.Board(action_points=1, played=("Slash", "Slash"), battle=("Chrono Archon", "Slash", "Slash")), ["Time Paradox", "Slash"]),
            # Generic play reads its 120% once, so a 180 card for 1 AP outbids the 240% it deals at Cost 2.
            ("Fate Imprint hits once for each point of its Cost", ("Amber Lumen", "Fate Imprint"), cards.Board(action_points=2), ["Fate Imprint"]),
            # Live, generic play rated it a flat 100 and played it last or not at all.
            ("Chrono Circle is worth its Fate Imprints", ("Amber Lumen", "Chrono Circle"), cards.Board(action_points=1), ["Chrono Circle"]),
            ("Chrono Circle goes ahead of the attacks", ("Slash", "Chrono Circle"), cards.Board(action_points=2), ["Chrono Circle", "Slash"]),
            ("Chrono Archon still outbids Chrono Circle", ("Chrono Circle", "Chrono Archon"), cards.Board(action_points=1), ["Chrono Archon"]),
        ))

    def test_selena_marks_before_attacking(self):
        """Marks make each later attack card fire an extra attack, so the cards that give them go before the attacks."""
        for description, cards_in_hand, expected in (
            # Generic play files the Mark skill after the attacks, so the Marks wait for next turn.
            ("High-Power Scope goes before the attack", ("Engagement Fire", "High-Power Scope"), ["High-Power Scope", "Engagement Fire"]),
            # Generic play buys the 210% attack first and plays it first, before Target Spotted's Mark.
            ("Target Spotted leads the attacks", ("Cold Shot", "Target Spotted"), ["Target Spotted", "Cold Shot"]),
            ("Drone Bombing goes before the plain attack", ("Cold Shot", "Drone Bombing"), ["Drone Bombing", "Cold Shot"]),
            ("the Marks come before Drone Bombing", ("Drone Bombing", "Target Spotted", "High-Power Scope"),
             ["High-Power Scope", "Target Spotted", "Drone Bombing"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), cards.Board())), expected)

    def test_every_kit_names_real_cards(self):
        # A game patch that renames a card would otherwise switch its kit off without a word.
        for kit in kits.KITS:
            for name in kit.cards | set(kit.places):
                with self.subTest(kit=kit.name, card=name):
                    self.assertIn(name, cards.CARD_COST)


if __name__ == "__main__":
    unittest.main()
