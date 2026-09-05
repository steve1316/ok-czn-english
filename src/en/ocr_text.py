"""Let the reverse OCR catalog match game text the client drew an icon into.

A card's type icon shares its OCR box with the label, so the reader hands back "4Upgrade", "ZUpgrade" or
"@skill" where the catalog only knows "Upgrade" and "Skill". The framework looks the text up whole-string with
one space-stripped retry, so each of those misses and the English label survives into the handler, which then
fails the four-character length test in `_card_has_type_below` and never sees the card at all.

Adding an entry per misreading does not converge - the icon is read differently almost every frame. This
retries the lookup instead, ignoring letter case and a short run of leading junk, so one rule covers the
variants that have not happened yet.
"""

import re

from ok import Logger

logger = Logger.get_logger(__name__)

# Only short text is worth retrying. Type labels and button captions are a few characters; a card's description
# is a sentence, and trimming its first letters could only ever produce a false match.
MAX_LENGTH = 30
# The icon is one glyph, but it sometimes splits into two. Beyond that a trim stops being a misread prefix.
MAX_PREFIX = 2
# Never trim down to something so short that it matches by accident.
MIN_REMAINDER = 3
# The icon sometimes lands after the caption instead, where OCR reads it as a stray short word.
# Only a one- or two-character tail counts - anything longer is a real word, or a half-drawn one.
MAX_TRAILING = 2

# Some captions are templates the client fills in, so no fixed msgid can ever match them all: the client
# ships more than fifty "Select {0} card(s) to X." strings, and the count varies per screen. These rewrite the
# whole family at once. Only the actions a handler actually looks for are listed - an unrecognised screen is
# better left in English than given an invented literal.
PATTERNS = (
    (re.compile(r"^select (?:up to )?(\d+) cards? ?\(?s?\)? to remove.*$", re.I), "请选择{0}张要移除的卡牌"),
    (re.compile(r"^select (?:up to )?(\d+) cards? ?\(?s?\)? to convert.*$", re.I), "请选择{0}张转换的卡牌"),
    (re.compile(r"^select (?:up to )?(\d+) cards? ?\(?s?\)? to duplicate.*$", re.I), "请选择{0}张复制的卡牌"),
    (re.compile(r"^select (?:up to )?(\d+) cards? ?\(?s?\)? to (?:spark|trigger).*epiphany.*$", re.I), "请选择{0}张闪光的卡牌"),
    (re.compile(r"^select \w+ combatant to join.*$", re.I), "请选择加入的主战员"),
)

_patched = False


def without_trailing_glyph(text):
    """Drop a stray short token the icon left at the end of the caption.

    Args:
        text: The box text, already stripped.

    Returns:
        The text without its trailing glyph, or None when the tail is a real word.
    """
    head, separator, tail = text.rpartition(" ")
    if not separator or len(tail.strip(".,:;!?")) > MAX_TRAILING:
        return None
    head = head.strip()
    return head if len(head) >= MIN_REMAINDER else None


def normalised_forms(text):
    """Yield the lookup keys to try for a reading the catalog did not recognise.

    Args:
        text: The box text, already stripped.

    Returns:
        A generator of casefolded candidate keys, longest first.
    """
    seen = set()
    for start in range(MAX_PREFIX + 1):
        trimmed = text[start:].strip()
        if len(trimmed) < MIN_REMAINDER:
            return
        # Trimming only ever shortens the text, so a caption caught half-drawn stays unmatched rather than
        # matching the longer msgid it is on its way to becoming.
        for candidate in (trimmed, without_trailing_glyph(trimmed)):
            if candidate is None:
                continue
            for form in (candidate, candidate.replace(" ", "")):
                key = form.casefold()
                if key not in seen:
                    seen.add(key)
                    yield key


def lookup_for(translation):
    """Build the catalog's msgids keyed for case- and space-insensitive matching.

    Args:
        translation: The gettext translation holding `ocr.po`.

    Returns:
        A dict of casefolded msgid to msgstr, cached on the translation itself.
    """
    lookup = getattr(translation, "_en_normalised_lookup", None)
    if lookup is None:
        lookup = {}
        for msgid, msgstr in getattr(translation, "_catalog", {}).items():
            if not msgid or not msgstr:
                continue
            lookup.setdefault(msgid.casefold(), msgstr)
            lookup.setdefault(msgid.replace(" ", "").casefold(), msgstr)
        translation._en_normalised_lookup = lookup
        logger.info(f"normalised OCR lookup built from {len(lookup)} catalog keys")
    return lookup


def fix_for(translation, text):
    """Find the Chinese literal for a reading the framework's own lookup missed.

    Args:
        translation: The gettext translation holding `ocr.po`.
        text: The box text, already stripped.

    Returns:
        The catalog's translation, or None when nothing matches.
    """
    if not text:
        return None
    if len(text) <= MAX_LENGTH:
        lookup = lookup_for(translation)
        for key in normalised_forms(text):
            fix = lookup.get(key)
            if fix is not None and fix != text:
                return fix
    return pattern_fix(text)


def pattern_fix(text):
    """Rewrite a caption the client builds from a template.

    Args:
        text: The box text, already stripped.

    Returns:
        The Chinese literal the handler compares against, or None when no rule applies.
    """
    stripped = text.strip()
    for pattern, template in PATTERNS:
        found = pattern.match(stripped)
        if found:
            return template.format(*found.groups())
    return None


def apply():
    """Widen `OCR.fix_texts` so icon-mangled readings still reach the catalog."""
    global _patched
    if _patched:
        return
    # Defined on OCR, so patching there covers BaseTask and TriggerTask and anything else deriving from it.
    from ok.task.task import OCR

    original_fix_texts = OCR.fix_texts

    def patched_fix_texts(self, detected_boxes):
        # Run upstream first and only reconsider what it left alone, so its exact matches always win and the
        # patch keeps working if upstream changes how it looks text up.
        before = [box.name.strip() for box in detected_boxes]
        original_fix_texts(self, detected_boxes)
        translation = getattr(self.executor, "ocr_po_translation", None)
        if translation is None:
            return
        for box, was in zip(detected_boxes, before):
            if box.name != was:
                continue
            if fix := fix_for(translation, was):
                logger.debug(f"normalised {was} -> {fix}")
                box.name = fix

    OCR.fix_texts = patched_fix_texts
    _patched = True
