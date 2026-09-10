"""Guard the reverse OCR catalog that lets the CN handlers run against the Global client.

`i18n/<locale>/LC_MESSAGES/ocr.po` maps English game text onto the Chinese literals `ok_tasks/` compares
against. The framework applies it in `Task.fix_texts()`, so a malformed catalog fails silently at runtime -
handlers simply stop matching. These tests fail loudly instead.
"""

import gettext
import re
import unittest
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N_ROOT = REPO_ROOT / "i18n"
LOCALES = ("en_US", "zh_CN")
CJK = re.compile(r"[\u4e00-\u9fff]")


def ocr_po(locale):
    """Build the path to one locale's reverse OCR catalog source.

    Args:
        locale: Locale directory name, such as `en_US`.

    Returns:
        A `Path` to `i18n/<locale>/LC_MESSAGES/ocr.po`.
    """
    return I18N_ROOT / locale / "LC_MESSAGES" / "ocr.po"


def entries(locale):
    """Read the live entries of one locale's reverse OCR catalog.

    Args:
        locale: Locale directory name, such as `en_US`.

    Returns:
        A list of `polib.POEntry`, excluding obsolete entries and the header.
    """
    return [e for e in polib.pofile(str(ocr_po(locale))) if not e.obsolete and e.msgid]


def is_english_side(msgid):
    """Report whether a msgid reads as game text from an English client.

    OCR sometimes attaches a stray CJK glyph to a button whose label is otherwise Latin, because it tries to
    read the icon beside it. Those readings belong here. What does not belong is a Chinese UI label, which
    would mean an `ok.po` entry was filed in this catalog by mistake.

    Args:
        msgid: The msgid to judge.

    Returns:
        True when the msgid carries Latin letters and is not predominantly Chinese.
    """
    if not any(ch.isascii() and ch.isalpha() for ch in msgid):
        return False
    return len(CJK.findall(msgid)) * 2 < len(msgid)


class TestOcrCatalog(unittest.TestCase):

    def test_entries_are_well_formed(self):
        """Every entry must be English on the left, non-empty on the right, and name the call site it serves.

        A Chinese msgid means a UI string was filed here by mistake. UI labels belong in `ok.po`, which runs the
        other way, and one landing here would rewrite game text instead of a label. An empty msgstr makes gettext
        return the msgid, so the English would reach the handlers untranslated. The `# From <handler>` comment is
        what keeps upstream merges mechanical - the new Chinese literals a merge brings in get diffed against it.
        """
        for locale in LOCALES:
            for entry in entries(locale):
                with self.subTest(locale=locale, msgid=entry.msgid):
                    self.assertTrue(is_english_side(entry.msgid), "msgid is Chinese, it belongs in ok.po")
                    self.assertTrue(entry.msgstr.strip(), "no translation")
                    self.assertIn("From", (entry.comment or "") + (entry.tcomment or ""), "no '# From <handler>' comment")

    def test_locales_stay_in_step(self):
        """Both locales must carry the same entries.

        The catalog is keyed on the app UI locale, not on the game client, so someone playing the Global client
        with a Chinese UI reads `zh_CN/ocr.po`. `fix_texts` fails open, so an entry added to one file and not the
        other loses every handler that depends on it with no error at all - the handlers just stop matching.
        """
        maps = {locale: {e.msgid: e.msgstr for e in entries(locale)} for locale in LOCALES}
        first, *rest = LOCALES
        for locale in rest:
            self.assertEqual(maps[first], maps[locale], f"{first} and {locale} ocr.po have drifted apart")

    def test_equipment_stats_resolve_to_a_slot(self):
        """_EQUIPMENT_TYPE_SLOTS does a substring test on the stat row, so a short literal silently misses."""
        slots = {"攻击力": 0, "防御力": 1, "生命值": 2}
        translation = gettext.translation("ocr", str(I18N_ROOT), languages=["en_US"])
        for stat, expected in (("Attack", 0), ("Defense", 1), ("Health", 2)):
            with self.subTest(stat=stat):
                # The row reads as one string once _get_region_text joins the boxes, hence the trailing value.
                row = translation.gettext(stat) + "+60"
                self.assertEqual(expected, next((s for k, s in slots.items() if k in row), None))

    def test_the_attack_label_still_reads_as_a_card_type(self):
        """Attack is shared with the card type label, which is why it is widened rather than replaced."""
        keywords = {"攻击", "强化", "技能", "技", "咒术", "诅咒", "攻", "击", "基础", "基本", "状态", "异常"}
        translation = gettext.translation("ocr", str(I18N_ROOT), languages=["en_US"])
        attack = translation.gettext("Attack")
        self.assertTrue(any(keyword in attack for keyword in keywords))
        # _card_has_type_below only looks at boxes of four characters or fewer.
        self.assertLessEqual(len(attack), 4)

    def test_the_card_reward_title_is_mapped(self):
        """Without it the page is never identified and handle_unknown_page clicks at random until it lands."""
        translation = gettext.translation("ocr", str(I18N_ROOT), languages=["en_US"])
        title = translation.gettext("Card Reward")
        # handle_card_reward joins every box in the title strip before testing, hence the trailing text.
        self.assertIn("卡牌奖励", title + "666")

    def test_the_purchase_card_title_is_mapped(self):
        """Without it handle_card_assign never sees a purchase, so it picks a combatant and never buys."""
        translation = gettext.translation("ocr", str(I18N_ROOT), languages=["en_US"])
        self.assertIn("购买卡牌", translation.gettext("Purchase Card"))

    def test_the_recommended_banner_is_mapped(self):
        """src/en/equipment.py pairs this banner with a combatant row; unmapped, the row is never preferred."""
        translation = gettext.translation("ocr", str(I18N_ROOT), languages=["en_US"])
        self.assertEqual("推荐", translation.gettext("Recommended"))

    def test_compiled_catalog_is_current(self):
        """Read the catalog the way the framework does, since the app only ever loads the compiled .mo.

        This covers staleness as well as loading: a `.po` entry that was never compiled does not come back.
        """
        for locale in LOCALES:
            self.assertTrue(ocr_po(locale).with_suffix(".mo").exists(), f"missing {locale} ocr.mo, run scripts/compile_i18n.py")
            translation = gettext.translation("ocr", localedir=str(I18N_ROOT), languages=[locale])
            for entry in entries(locale):
                with self.subTest(locale=locale, msgid=entry.msgid):
                    self.assertEqual(entry.msgstr, translation.gettext(entry.msgid), "stale .mo, run scripts/compile_i18n.py")


if __name__ == "__main__":
    unittest.main()
