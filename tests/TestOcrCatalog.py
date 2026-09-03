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
LOCALES = ("en_US", "zh_CN")
CJK = re.compile(r"[\u4e00-\u9fff]")


def catalog_path(locale, domain):
    """Build the path to one compiled or source catalog.

    Args:
        locale: Locale directory name, such as `en_US`.
        domain: Catalog domain, either `ocr` or `ok`.

    Returns:
        A `Path` to `i18n/<locale>/LC_MESSAGES/<domain>`, without a suffix.
    """
    return REPO_ROOT / "i18n" / locale / "LC_MESSAGES" / domain


def entries(locale):
    """Read the live entries of one locale's reverse OCR catalog.

    Args:
        locale: Locale directory name, such as `en_US`.

    Returns:
        A list of `polib.POEntry`, excluding obsolete entries and the header.
    """
    po = polib.pofile(str(catalog_path(locale, "ocr").with_suffix(".po")))
    return [e for e in po if not e.obsolete and e.msgid]


class TestOcrCatalog(unittest.TestCase):

    def test_catalogs_exist_for_every_locale(self):
        """Both the source and the compiled catalog must be present, since the app only reads the .mo."""
        for locale in LOCALES:
            base = catalog_path(locale, "ocr")
            self.assertTrue(base.with_suffix(".po").exists(), f"missing {locale} ocr.po")
            self.assertTrue(base.with_suffix(".mo").exists(), f"missing {locale} ocr.mo, run scripts/compile_i18n.py")

    def test_compiled_catalog_matches_source(self):
        """A .po edit that was never compiled is invisible at runtime."""
        for locale in LOCALES:
            base = catalog_path(locale, "ocr")
            want = {e.msgid: e.msgstr for e in entries(locale)}
            have = {e.msgid: e.msgstr for e in polib.mofile(str(base.with_suffix(".mo"))) if e.msgid}
            self.assertEqual(want, have, f"{locale} ocr.mo is stale, run scripts/compile_i18n.py")

    def test_msgids_are_the_english_side(self):
        """This catalog runs English to Chinese. A Chinese msgid means a UI string was filed here by mistake.

        UI labels belong in `ok.po`, which runs the other way. Putting one here would rewrite game text.
        """
        for locale in LOCALES:
            for entry in entries(locale):
                self.assertIsNone(CJK.search(entry.msgid), f"{locale}: msgid '{entry.msgid}' contains Chinese, it belongs in ok.po")

    def test_every_entry_translates_to_something(self):
        """An empty msgstr makes gettext return the msgid, so the English text would reach the handlers."""
        for locale in LOCALES:
            for entry in entries(locale):
                self.assertTrue(entry.msgstr.strip(), f"{locale}: '{entry.msgid}' has no translation")

    def test_every_entry_names_its_call_site(self):
        """Each entry carries a `# From <handler>: <literal>` comment.

        That provenance is what makes an upstream merge mechanical - the new Chinese literals a merge brings in
        can be diffed against these comments to find what still needs an English entry.
        """
        for locale in LOCALES:
            for entry in entries(locale):
                comment = (entry.comment or "") + (entry.tcomment or "")
                self.assertIn("From", comment, f"{locale}: '{entry.msgid}' has no '# From <handler>' comment")

    def test_translation_round_trips_through_gettext(self):
        """Read the catalog the way the framework does, so a bad encoding or plural form shows up here."""
        for locale in LOCALES:
            translation = gettext.translation("ocr", localedir=str(REPO_ROOT / "i18n"), languages=[locale])
            for entry in entries(locale):
                self.assertEqual(entry.msgstr, translation.gettext(entry.msgid), f"{locale}: '{entry.msgid}' did not round trip")


if __name__ == "__main__":
    unittest.main()
