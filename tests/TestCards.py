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
# Two Action Points for 220% damage, which is better value per point than 100% for one.
BIG_ATTACK = "Charge Launcher"
# Spends every Action Point left rather than a fixed number.
SPENDS_EVERYTHING = "Absolute Protection"
# Costs nothing and, now and then, ends the fight outright.
ESCAPE = "Fear"


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

    def test_nothing_affordable_plays_nothing(self):
        self.assertEqual(cards.plan(hand(JUSTICE_ATTACK), cards.Board(action_points=0)), [])


class TestOrdering(unittest.TestCase):
    """The order a turn is played in, which is most of what separates good play from legal play."""

    def test_a_free_card_goes_before_one_that_costs_anything(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, FREE_ATTACK), cards.Board())
        self.assertEqual(played(chosen)[0], FREE_ATTACK)

    def test_a_buff_goes_before_an_attack(self):
        # Both cost one, so only the rule that a Power card should land before the attack it improves can
        # decide this.
        chosen = cards.plan(hand(JUSTICE_ATTACK, BUFF), cards.Board())
        self.assertEqual(played(chosen), [BUFF, JUSTICE_ATTACK])

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
        # Spending a point on the buff would leave nothing for the two-point attack. Which cards get played
        # has to be settled on what they are worth, and only then put in the order they are played in.
        chosen = cards.plan(hand(BUFF, BIG_ATTACK), cards.Board(action_points=2))
        self.assertEqual(played(chosen), [BIG_ATTACK])

    def test_a_tight_budget_buys_the_better_attack(self):
        chosen = cards.plan(hand(JUSTICE_ATTACK, BIG_ATTACK), cards.Board(action_points=2))
        self.assertEqual(played(chosen), [BIG_ATTACK])

    def test_every_hit_of_a_multi_hit_attack_counts(self):
        # 40% three times is 120%, which beats 100% once. Read as its first hit alone it lost to it.
        chosen = cards.plan(hand(JUSTICE_ATTACK, "Aggressive Assault"), cards.Board(action_points=1))
        self.assertEqual(played(chosen), ["Aggressive Assault"])


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
        # "Quant" is "Quantum Seed", and only one letter from the start of "Attack" once the type icon is trimmed off.
        for stub in ("Quant", "NA:Defens"):
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
        for description, reading, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(cards.canonical(reading), expected)

    def test_a_card_the_data_never_heard_of_is_still_played(self):
        chosen = cards.plan(hand("Some Card From A Later Patch"), cards.Board())
        self.assertEqual(len(chosen), 1)

    def test_an_unreadable_card_does_not_stop_the_rest_of_the_turn(self):
        chosen = cards.plan(hand("", JUSTICE_ATTACK), cards.Board())
        self.assertIn(JUSTICE_ATTACK, played(chosen))


class TestKits(unittest.TestCase):
    """Playstyles the generic value per point cannot see."""

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
        ):
            with self.subTest(description):
                self.assertCountEqual(played(cards.plan(hand(*cards_in_hand), cards.Board())), expected)

    def test_luke_fires_his_bullets_before_cashing_them_in(self):
        """Finisher Round unlocks after five Handgun Bullets this turn, and Dance of the Demon gains a hit per Bullet fired."""
        five_fired = ("Magnum Shot", "Magnum Shot", "Silver Shot", "Uranium Shot", "Tracer Shot")
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_hugo_builds_stacks_before_spending_them(self):
        """Commence the Hunt stacks come from skills and Dingo Howling and Fan of Daggers, and attacks spend them."""
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_owen_lands_wind_charge_on_an_attack(self):
        """Wind Charge adds a hit to Owen's next attack, and Wind Riding fetches it back from the discard pile."""
        for description, cards_in_hand, board, expected in (
            # Generic play spends a point on a hit no Owen attack will take.
            ("Wind Charge waits for an Owen attack", ("Wind Charge", "Weapon Block"), cards.Board(), ["Weapon Block"]),
            ("Break Armor goes first, so it does not take the hit", ("Wind Charge", "Break Armor"), cards.Board(), ["Break Armor"]),
            ("Wind Charge lands between Break Armor and the attack", ("Wind Charge", "Gale Strike", "Break Armor"),
             cards.Board(action_points=4), ["Break Armor", "Wind Charge", "Gale Strike"]),
            # Generic play buys the 100% attack over a shield worth 90.
            ("Wind Riding is bought to fetch last turn's Wind Charge", ("Downward Cut", "Wind Riding"),
             cards.Board(action_points=1, last_turn=("Wind Charge",)), ["Wind Riding"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_lucas_plays_sss_before_the_bullets(self):
        """S.S.S buffs the Launcher Bullets played after it for the turn."""
        for description, cards_in_hand, board, expected in (
            # Generic play ranks it as a plain 100% attack, below the 210 bullet, so it lands after it.
            ("S.S.S goes before the bullets it buffs", ("Flame Shot", "S.S.S"), cards.Board(action_points=2), ["S.S.S", "Flame Shot"]),
            # Generic play keeps hand order between the two 100% attacks.
            ("S.S.S goes before a plain attack", ("Machine Gun", "S.S.S"), cards.Board(action_points=2), ["S.S.S", "Machine Gun"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_magna_plays_her_lead_cards_first(self):
        """Ice Fragment and Storm of Bitter Cold lose their Lead discount once another card has been played."""
        for description, cards_in_hand, board, expected in (
            # Generic play spends the free card first.
            ("Ice Fragment goes before a free card", ("Adagio", "Ice Fragment"), cards.Board(action_points=1), ["Ice Fragment", "Adagio"]),
            ("Storm of Bitter Cold goes before a free card", ("Adagio", "Storm of Bitter Cold"), cards.Board(action_points=1),
             ["Storm of Bitter Cold", "Adagio"]),
            # Pins the release: the discount is gone once a card is played, so the free card keeps its usual place.
            ("Ice Fragment keeps its place once a card is played", ("Ice Fragment", "Adagio"),
             cards.Board(action_points=1, played=(JUSTICE_ATTACK,)), ["Adagio", "Ice Fragment"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_maribell_fires_shelter_strike_after_her_shields(self):
        """Shelter Strike deals Fixed Damage equal to the Shield she owns."""
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_mei_lin_buffs_first_and_ends_on_the_spire(self):
        """Rising Dragon Spire gains hits from the cards before it, and Spirit of the Aromata buffs the cards after it."""
        for description, cards_in_hand, board, expected in (
            # Generic play keeps hand order among the attacks.
            ("the Spire follows the Strikes", ("Rising Dragon Spire", "Strike", "Strike"), cards.Board(action_points=3),
             ["Strike", "Strike", "Rising Dragon Spire"]),
            # Generic play puts the buff after the attacks it was meant to raise.
            ("Spirit goes before the attacks", ("Strike", "Spirit of the Aromata"), cards.Board(action_points=2),
             ["Spirit of the Aromata", "Strike"]),
            # Generic play buys Sovereignty's 300% for the two points, ahead of two Strikes.
            ("Sovereignty does not take the points from the Strikes", ("Flame Dragon's Sovereignty", "Strike", "Strike"),
             cards.Board(action_points=2), ["Strike", "Strike"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_mika_spends_points_on_the_partner_first(self):
        """Water Arrow, Water Barrier and Whirlpool are cut from her deck by the guides, so a partner's card is bought first."""
        for description, cards_in_hand, board, expected in (
            # Generic play ties Water Arrow with the partner's 100% attack and takes the one that comes first in hand.
            ("a partner attack beats Water Arrow", ("Water Arrow", JUSTICE_ATTACK), cards.Board(action_points=1), [JUSTICE_ATTACK]),
            ("a partner attack beats Water Barrier", ("Water Barrier", JUSTICE_ATTACK), cards.Board(action_points=1), [JUSTICE_ATTACK]),
            # Generic play ties Whirlpool's 100 per point with the attacks and takes it first.
            ("two partner attacks beat Whirlpool", ("Whirlpool", JUSTICE_ATTACK, JUSTICE_ATTACK), cards.Board(action_points=2),
             [JUSTICE_ATTACK, JUSTICE_ATTACK]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_narja_sets_up_before_the_attacks(self):
        """Voluntary Control makes Voracity and Domain of Voracity raises Tenacity damage, and both only help the attacks after them."""
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_nia_orders_her_cycling_cards(self):
        """Adagio leaves a discard on top for G Chord, Soul Riff counts later discards, and Mute Accent discards the dearest card."""
        for description, cards_in_hand, board, expected in (
            # Generic play puts the skill after the attack.
            ("G Chord goes before the attacks", (JUSTICE_ATTACK, "G Chord"), cards.Board(action_points=2), ["G Chord", JUSTICE_ATTACK]),
            # Generic play runs the free discarder first, so Soul Riff counts none of it.
            ("Soul Riff goes before Adagio", (FREE_DRAW, "Soul Riff"), cards.Board(action_points=1), ["Soul Riff", FREE_DRAW]),
            ("Curiosity goes before the attacks", (JUSTICE_ATTACK, "Nia’s Curiosity"), cards.Board(action_points=2),
             ["Nia’s Curiosity", JUSTICE_ATTACK]),
            # Generic play throws the 2 AP card away along with its own 220%.
            ("Mute Accent waits while a dearer card is in hand", ("Mute Accent", BIG_ATTACK), cards.Board(action_points=3), [BIG_ATTACK]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_adelheid_sets_up_and_waits_for_a_pack(self):
        """Once Upon A Time blesses before Protect Us draws, Garden of Secrets is a top spend, and Doggie (Pack) comes in twos."""
        for description, cards_in_hand, board, expected in (
            # Generic play keeps hand order, so Protect Us draws Blessing cards before any exist.
            ("Once Upon A Time goes before Protect Us", ("Protect Us", "Once Upon A Time"), cards.Board(), ["Once Upon A Time", "Protect Us"]),
            # Generic play rates Garden's 200% shield at 120 and buys the 200% attack ahead of it.
            ("Garden of Secrets ties her best attack", ("Garden of Secrets", "Truth Behind A Story"), cards.Board(action_points=1),
             ["Garden of Secrets"]),
            # Generic play plays the free Doggie at once.
            ("a lone Doggie (Pack) waits", ("Doggie (Pack)", "Gather Around"), cards.Board(), ["Gather Around"]),
            # Pins the hold being released, so it passes without the kit too.
            ("two Doggie (Pack) are played", ("Doggie (Pack)", "Doggie (Pack)"), cards.Board(), ["Doggie (Pack)", "Doggie (Pack)"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_amir_builds_metalization_and_ends_on_iron_skin(self):
        """Hovering Metal and Metal Extraction give Metalization first, Iron Skin ends the turn, and Steel Barrier sets off a hit after Hurricane."""
        for description, cards_in_hand, board, expected in (
            # Generic play puts the generators in the late skill phase, after the attack that would spend their stacks.
            ("the generators go before the attacks", ("Rapier", "Hovering Metal"), cards.Board(action_points=2), ["Hovering Metal", "Rapier"]),
            # Generic play keeps hand order among the late skills, so the Finale ends the turn on top of the shield.
            ("Iron Skin goes after every other card", ("Iron Skin", "Steel Barrier"), cards.Board(action_points=2), ["Steel Barrier", "Iron Skin"]),
            # Generic play rates its 100% shield below Rapier's 100% hit.
            ("Steel Barrier beats Rapier once Hurricane is played", ("Rapier", "Steel Barrier"),
             cards.Board(action_points=1, played=("Full Metal Hurricane",)), ["Steel Barrier"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_anika_discounts_one_big_attack_and_ends_on_reloading(self):
        """Warming Up waits for a two-cost attack and plays just before it, Rampage Trigger lands four hits last, and Reloading ends the turn."""
        for description, cards_in_hand, board, expected in (
            # Generic play spends the free Finale first and throws the hand away.
            ("Reloading goes last", ("Reloading", "Shock Gun"), cards.Board(action_points=1), ["Shock Gun", "Reloading"]),
            # Generic play discounts a card that costs one anyway.
            ("Warming Up waits for a big attack", ("Warming Up", "Shock Gun"), cards.Board(action_points=2), ["Shock Gun"]),
            # Generic play prices its 100% line at a single hit, so Shock Gun and Blaster Swing take the points.
            ("Rampage Trigger is bought for its four hits", ("Rampage Trigger", "Blaster Swing", "Shock Gun"), cards.Board(),
             ["Shock Gun", "Rampage Trigger"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)
        # With only Rampage Trigger to discount, generic play still puts Warming Up ahead of Shock Gun and wastes the discount on it.
        board = cards.Board(hand=("Warming Up", "Shock Gun", "Rampage Trigger"))
        self.assertGreater(cards.phase("Warming Up", board), cards.phase("Shock Gun", board))

    def test_arabella_applies_fracture_before_it_detonates(self):
        """Scream For Me and Hollow Verdict apply Fracture, Sadistic Restraint detonates it, and The Art of Unmaking waits for it."""
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_beryl_lets_charged_shot_grow_in_hand(self):
        """Charged Shot only takes points nothing else wants, and Heavy Weapons Specialist creates its card before the attacks."""
        for description, cards_in_hand, board, expected in (
            # Generic play spends two points on the 270% Charged Shot at once, leaving one for a single attack.
            ("cheaper attacks take the points", ("Charged Shot", "Launcher", "Opening Found"), cards.Board(), ["Opening Found", "Launcher"]),
            # Pins the hold being released when the points would otherwise go unused, so it passes without the kit too.
            ("spare points go to Charged Shot", ("Charged Shot",), cards.Board(), ["Charged Shot"]),
            # Generic play files the Specialist with the late skills, after the attack.
            ("the Specialist goes before the attacks", ("Launcher", "Heavy Weapons Specialist"), cards.Board(action_points=2),
             ["Heavy Weapons Specialist", "Launcher"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_cassius_keeps_to_his_deck_cards(self):
        """Wild Card, Cards and Mana Field are filler, Triple 0 follows the attacks it counts, and Shuffle is a rescue."""
        for description, cards_in_hand, board, expected in (
            # Generic play buys the 220% Wild Card for two points and has none left for Pop Eyed Popper.
            ("filler yields to Joker and the Popper", ("Wild Card", "Joker", "Pop Eyed Popper"), cards.Board(), ["Joker", "Pop Eyed Popper"]),
            # Generic play plays the free Quest card first, before any attack has been counted.
            ("Triple 0 follows the attacks", ("Triple 0", "Dice Trick"), cards.Board(action_points=2), ["Dice Trick", "Triple 0"]),
            # Generic play shuffles the hand away after the draw.
            ("Shuffle waits while a card can be played", ("Shuffle", "Devil Dice"), cards.Board(), ["Devil Dice"]),
            # Pins the hold being released when nothing else is playable, so it passes without the kit too.
            ("Shuffle rescues a dead hand", ("Shuffle", CURSE), cards.Board(), ["Shuffle"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_chizuru_spends_her_buffs_on_one_shadow(self):
        """Shadow of the Moon waits for Oni Hunt and Tsukuyomi and plays last, Karmic Flames leads, and Tsukuyomi sits right before Oni Hunt."""
        for description, cards_in_hand, board, expected in (
            # Generic play spends Shadow of the Moon at once, with the Oni Hunt buff still unplayed.
            ("Shadow waits for the buffs", ("Shadow of the Moon", "Oni Hunt"), cards.Board(action_points=2), ["Oni Hunt"]),
            # Generic play keeps hand order among the attacks, so Shadow goes first.
            ("Shadow goes last", ("Shadow of the Moon", "Moonslash"), cards.Board(action_points=2), ["Moonslash", "Shadow of the Moon"]),
            # Generic play keeps hand order, so the curse lands after the other hit.
            ("Karmic Flames leads the attacks", ("Moonslash", "Karmic Flames"), cards.Board(action_points=2), ["Karmic Flames", "Moonslash"]),
            # Generic play plays the free Tsukuyomi ahead of every setup card, and so well before Oni Hunt.
            ("Tsukuyomi sits right before Oni Hunt", ("Tsukuyomi", BUFF, "Oni Hunt"), cards.Board(action_points=2), [BUFF, "Tsukuyomi", "Oni Hunt"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_diana_discards_her_quietus_attacks(self):
        """Quietus cards fire free when discarded, so Diana keeps them for Blooming Love and Heart Breaker rather than paying for them."""
        milk = "C\u2019mere, Milk & Pong!"
        for description, cards_in_hand, board, expected in (
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
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_fei_sets_up_before_drawing_and_cashing_in(self):
        """Formation must precede the draws, Blazing War Dance follows the Descent they gain, and Soulfire Dance wants the points left."""
        formation = "Exorcist\u2019s Formation"
        for description, cards_in_hand, board, expected in (
            # Generic play draws first, and Soliloquy discards the Formation it draws.
            ("Formation goes before the draws", ("Soliloquy", formation), cards.Board(), [formation, "Soliloquy"]),
            # Generic play fires the free War Dance at the start of the turn, with no Descent gained.
            ("Blazing War Dance goes after the attacks", ("Blazing War Dance", "Azure Flame"), cards.Board(), ["Azure Flame", "Blazing War Dance"]),
            # Generic play spends the points on the small cards, so Soulfire Dance is left with none.
            ("small cards are held for Soulfire Dance", ("Azure Flame", "Soulfire Dance", "Melancholy"), cards.Board(), ["Soulfire Dance"]),
        ):
            with self.subTest(description):
                self.assertEqual(played(cards.plan(hand(*cards_in_hand), board)), expected)

    def test_every_kit_names_real_cards(self):
        # A game patch that renames a card would otherwise switch its kit off without a word.
        for kit in kits.KITS:
            for name in kit.cards | set(kit.places):
                with self.subTest(kit=kit.name, card=name):
                    self.assertIn(name, cards.CARD_COST)


if __name__ == "__main__":
    unittest.main()
