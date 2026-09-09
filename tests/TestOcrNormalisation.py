"""Check that icon-mangled OCR readings still reach the reverse catalog.

`src/en/ocr_text.py` widens the framework's whole-string lookup, so the things that can break are all
behavioural: a reading that should normalise failing to, or - far worse - one normalising that should not.
Card descriptions are the hazard, since they contain the same words as the type labels and clicking on a
mistranslated description would send a handler to the wrong screen.

Every reading asserted here was taken from a real Chaos run, not invented.
"""

import gettext
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import ocr_text  # noqa: E402

# The prompt over the combatant list. OCR drops its full stop about half the time, and the handler that owns
# the Purchase Card screen does nothing at all until this matches.
ASSIGN_PROMPT = "请选择要接受卡牌的主战员"

# The four-character ceiling in _card_has_type_below, which is the whole reason these have to become Chinese.
TYPE_LABEL_MAX = 4

# Readings seen in the 2026-09-04 Chaos run, with the label the client actually drew.
ICON_READINGS = {
    "XBasic Attack": "基础攻击",
    "△Basic Skill": "基础技能",
    "④Basic Skill": "基础技能",
    "③Basic Skill": "基础技能",
    "④Skill": "技能",
    "△Skill": "技能",
    "©skill": "技能",
    "skill": "技能",
    "4Upgrade": "强化",
    "4 Upgrade": "强化",
    "ZUpgrade": "强化",
    "7Upgrade": "强化",
    # The icon lands after the caption on this one, read as a stray letter.
    "View original Q": "查看原件",
    "View original Q.": "查看原件",
}

# Card and event description text from the same run. None of it may ever be rewritten.
DESCRIPTIONS = [
    "When an Upgrade or",
    "Skill Card of another",
    "Spark an Epiphany for a",
    "Card of a different Combatant",
    "92% Damage to all",
    "Create 3 Homing",
    "Arrow in Draw Pile",
    "102% Shield",
    "Combatant is used,",
    "Decrease Health by 30%,",
    "Select and Remove2 Cards",
    # Caught mid fade-in. Trimming only shortens, so a half-drawn caption can never reach the full msgid.
    "Choose Epiphany Eff",
]


class TestOcrNormalisation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.translation = gettext.translation("ocr", str(REPO_ROOT / "i18n"), languages=["en_US"])

    def fix(self, text):
        """Run the normalising retry the way the patched `fix_texts` does.

        Args:
            text: The box text as OCR read it.

        Returns:
            The catalog's Chinese literal, or None when nothing matched.
        """
        return ocr_text.fix_for(self.translation, text)

    def test_icon_prefixed_readings_reach_the_catalog(self):
        for reading, expected in ICON_READINGS.items():
            with self.subTest(reading=reading):
                self.assertEqual(expected, self.fix(reading))

    def test_normalised_labels_clear_the_length_test(self):
        """A label only helps if it ends up short enough for _card_has_type_below to consider it."""
        for reading, expected in ICON_READINGS.items():
            with self.subTest(reading=reading):
                self.assertLessEqual(len(expected), TYPE_LABEL_MAX)

    def test_descriptions_are_never_rewritten(self):
        """These share vocabulary with the type labels, so a loose rule would silently corrupt them."""
        for text in DESCRIPTIONS:
            with self.subTest(text=text):
                self.assertIsNone(self.fix(text))

    def test_long_text_is_left_alone_outright(self):
        """The length guard is what stops a sentence being trimmed into a match."""
        self.assertGreater(len("When Commence the Hunt is activated"), ocr_text.MAX_LENGTH)
        self.assertIsNone(self.fix("When Commence the Hunt is activated"))

    def test_a_trim_never_leaves_a_stub(self):
        """Trimming down to one or two characters would match almost anything."""
        for text in ("Skill", "Attack"):
            with self.subTest(text=text):
                for form in ocr_text.normalised_forms(text):
                    self.assertGreaterEqual(len(form), ocr_text.MIN_REMAINDER)

    def test_a_real_trailing_word_is_never_trimmed(self):
        """Only a one- or two-character tail is icon debris; anything longer is part of the caption."""
        self.assertIsNone(ocr_text.without_trailing_glyph("Skill Card of another"))
        self.assertIsNone(ocr_text.without_trailing_glyph("Combatant is used,"))
        self.assertEqual("View original", ocr_text.without_trailing_glyph("View original Q."))

    def test_unknown_text_stays_unknown(self):
        self.assertIsNone(self.fix("Multishot"))
        self.assertIsNone(self.fix("Hunting Instincts"))

    def test_a_templated_caption_is_rewritten_whatever_the_count(self):
        """The client builds these from a template, so no fixed msgid can cover every count."""
        for count in (1, 2, 3, 4, 5, 9):
            with self.subTest(count=count):
                self.assertEqual(f"请选择{count}张要移除的卡牌",
                                 ocr_text.pattern_fix(f"Select {count} card(s) to Remove."))

    def test_every_action_a_handler_looks_for_is_covered(self):
        for caption, expected in (
            ("Select 1 card(s) to spark an Epiphany for.", "请选择1张闪光的卡牌"),
            ("Select 1 card(s) to trigger Epiphany.", "请选择1张闪光的卡牌"),
            ("Select 1 card(s) to Convert.", "请选择1张转换的卡牌"),
            ("Select 3 card(s) to Duplicate.", "请选择3张复制的卡牌"),
            ("Select up to 2 card(s) to Remove.", "请选择2张要移除的卡牌"),
            ("Select second Combatant to join.", "请选择加入的主战员"),
            ("Select fourth Combatant to join.", "请选择加入的主战员"),
        ):
            with self.subTest(caption=caption):
                self.assertEqual(expected, ocr_text.pattern_fix(caption))

    def test_an_action_no_handler_wants_is_left_in_english(self):
        """The client ships fifty of these. Inventing a literal for one nothing reads would be worse."""
        for caption in ("Select 1 card(s) to Discard.", "Select 2 card(s) to Exhaust.",
                        "Select 1 card(s) to move to Draw Pile."):
            with self.subTest(caption=caption):
                self.assertIsNone(ocr_text.pattern_fix(caption))

    def test_ordinary_text_is_never_rewritten_by_a_rule(self):
        for text in ("Tap and hold the card to view its details.", "Card Reward", "Prepare for Battle", ""):
            with self.subTest(text=text):
                self.assertIsNone(ocr_text.pattern_fix(text))

    def test_the_assign_prompt_matches_with_its_period(self):
        """The form the catalog carries, and the one a clean frame produces."""
        self.assertEqual(ASSIGN_PROMPT, self.fix("Select the combatant to receive the card."))

    def test_the_assign_prompt_matches_without_its_period(self):
        """A run stalled on Purchase Card for minutes because this frame dropped the full stop."""
        self.assertEqual(ASSIGN_PROMPT, self.fix("Select the combatant to receive the card"))

    def test_a_class_locked_combatant_is_recognised(self):
        """handle_card_assign excludes a row by this literal, so an unmapped class is clicked anyway."""
        for klass in ("Striker", "Vanguard", "Ranger", "Hunter", "Psionic", "Controller"):
            with self.subTest(klass=klass):
                self.assertIn("无法获得", ocr_text.pattern_fix(f"{klass} Unobtainable"))

    def test_only_a_real_class_reads_as_unobtainable(self):
        """A loose rule here would exclude every combatant and cancel the purchase."""
        for text in ("Unobtainable", "Loot Unobtainable", "This card is Unobtainable for now"):
            with self.subTest(text=text):
                self.assertIsNone(ocr_text.pattern_fix(text))

    def test_the_patch_is_idempotent(self):
        """globals.apply() runs once, but a second call must not wrap the patch inside itself."""
        from ok.task.task import OCR
        ocr_text.apply()
        once = OCR.fix_texts
        ocr_text.apply()
        self.assertIs(once, OCR.fix_texts)


if __name__ == "__main__":
    unittest.main()
