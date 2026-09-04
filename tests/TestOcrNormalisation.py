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

    def test_the_patch_is_idempotent(self):
        """globals.apply() runs once, but a second call must not wrap the patch inside itself."""
        from ok.task.task import OCR
        ocr_text.apply()
        once = OCR.fix_texts
        ocr_text.apply()
        self.assertIs(once, OCR.fix_texts)


if __name__ == "__main__":
    unittest.main()
