"""Read the deck off the All Piles view once a Sortie layer, so every card is valued by the Epiphany it really carries.

A card in hand shows only its name, and the data holds a card's base text beside every Epiphany it could take, so the picker valued an
Epiphany card by its base text. Upstream never opens the view. This reads it on the information page trip that reads the team.
"""

import difflib
import re

from ok import Logger

from src.en import cards
from src.en.game_text import DESCRIPTIONS, EPIPHANIES
from src.en.handlers import loaded, register, standing_in, wrap
from src.en.quality import fold
from src.en.screen import PAGE_CLOSE, centre_of, lines_in, raw_ocr, text_in_region
from src.en.stuck import forget

logger = Logger.get_logger(__name__)

# Where the information page's left rail draws the deck icon that opens All Piles.
PILES_TAB = (0.042, 0.282)
# The view's title, which the reader also returns as "AIll Piles".
TITLE = "Piles"
TITLE_REGION = (0.05, 0.0, 0.3, 0.1)
# The four card columns of the grid, left to right, as fractions of the screen width.
COLUMNS = ((0.315, 0.461), (0.481, 0.627), (0.646, 0.792), (0.810, 0.956))
# How far below a card name's centre its type label sits, which tells a name from a card named inside another card's text.
LABEL_GAP = (0.01, 0.045)
# Where a card's effect text sits below its name's centre. A card whose text runs off the bottom is read on a later page.
TEXT_BAND = (0.05, 0.35)
# Names above this are under the title bar.
TITLE_BAR = 0.1
# Where and how far to scroll the grid per page. Upstream's -3 took 7 pages to cross a 16-card deck's 4 rows, and a card stays whole
# for about 0.55 of the screen, so twice that still reads every card at least once.
SCROLL_POINT = (0.63, 0.55)
SCROLL_AMOUNT = -6
# Pages read before giving up on reaching the bottom, enough for about 9 rows at that scroll.
MAX_PAGES = 15
# How closely a card's text has to match a version of it to be taken for that version, letters only.
MATCH_FLOOR = 0.5
# A keyword tag like "[Unique / Initiation]", which the data keeps out of a card's text.
KEYWORD_TAGS = re.compile(r"\[[^\]]*\]")
NOT_A_LETTER = re.compile(r"[^a-z]")
# Holds in `node_status` that this layer's deck has been read. Upstream rebuilds `node_status` as a layer starts.
READ = "_en_piles_read"
# Only Sortie reads the deck, though Chaos runs the same capture.
SORTIE_MODE = "SortieMode"
TAG = "reads the deck before closing"

_patched = False


def signature(text):
    """Strip an effect text down to the letters of its wording.

    The numbers move with upgrades and the reader runs words together ("for1turn"), so only the letters are compared.

    Args:
        text: An effect text, read off the screen or from the data.

    Returns:
        The lowercase letters, without keyword tags.
    """
    return NOT_A_LETTER.sub("", KEYWORD_TAGS.sub("", text).lower())


def version_of(name, text):
    """Find which version of a card a text read off the screen is.

    Args:
        name: The canonical card name.
        text: The card's effect text as read.

    Returns:
        The data's text for the closest version: the base, or one of its `EPIPHANIES`. The base when nothing comes close.
    """
    base = DESCRIPTIONS.get(name) or ""
    read = signature(text)
    best, best_score = base, MATCH_FLOOR
    for version in (base, *EPIPHANIES.get(name, ())):
        score = difflib.SequenceMatcher(None, read, signature(version)).ratio()
        if score > best_score:
            best, best_score = version, score
    return best


def cards_on_page(task):
    """Read every whole card on the current page of the grid.

    Args:
        task: The running task, whose `all_texts` holds this page's OCR pass.

    Returns:
        `(name, text, y)` for each card whose name, type label and text are all on screen, `y` being the name's centre.
    """
    centres = [(box, *centre_of(box, task.width, task.height)) for box in task.all_texts]
    found = []
    for left, right in COLUMNS:
        column = [(box, y) for box, x, y in centres if left <= x <= right]
        for box, y in column:
            name = cards.canonical(box.name)
            if name not in cards.CARD_COST or not TITLE_BAR < y < 1 - TEXT_BAND[1]:
                continue
            if not any(LABEL_GAP[0] < other_y - y < LABEL_GAP[1] and cards.looks_like_label(fold(other.name)) for other, other_y in column):
                continue
            found.append((name, lines_in(task, (left, y + TEXT_BAND[0], right, y + TEXT_BAND[1])), round(y, 2)))
    return found


def read_piles(task, utils):
    """Page through All Piles and match every card read to its version.

    Args:
        task: The running task, on the All Piles view.
        utils: The loaded `utils` module, for upstream's scroll.

    Returns:
        Canonical card name to the set of version texts its copies matched.
    """
    copies = {}
    last_page = None
    for _ in range(MAX_PAGES):
        raw_ocr(task)
        page = cards_on_page(task)
        # The same names at the same heights means the scroll did not move, so this is the bottom.
        where = [(name, y) for name, _, y in page]
        if where == last_page:
            break
        for name, text, _ in page:
            copies.setdefault(name, set()).add(version_of(name, text))
        last_page = where
        utils._scroll_card_page(task, *SCROLL_POINT, SCROLL_AMOUNT, "All Piles")
    return copies


def read_deck(task, utils):
    """Open All Piles from the information page and read the deck.

    Args:
        task: The running Sortie task, on the information page.
        utils: The loaded `utils` module, for upstream's tap and scroll.
    """
    utils._move_and_click(task, *PILES_TAB)
    task.sleep(1)
    raw_ocr(task, task.box_of_screen(*TITLE_REGION))
    if text_in_region(task, TITLE, TITLE_REGION) is None:
        logger.warning("tapped the deck icon but All Piles did not open, keeping the last deck read")
        return
    copies = read_piles(task, utils)
    cards.use_deck(copies)
    epiphanies = sorted(name for name, texts in copies.items() if texts - {DESCRIPTIONS.get(name)})
    logger.info(f"read {len(copies)} distinct cards off All Piles, {len(epiphanies)} with an Epiphany: {epiphanies}")
    logger.debug(f"deck read: {sorted(copies)}")
    # The read held one frame for seconds, which upstream's stuck detector would take for a frozen screen and close the page over.
    forget(task)


def reading_the_deck(handler, utils_chaos):
    """Read the deck once a Sortie layer, between upstream's team capture and the tap that closes the page.

    All Piles draws its X where the information page does, so the one close tap shuts both, with no tap back to the Combatants tab.

    Args:
        handler: Upstream's `handle_archive_target_member`, as the other modules have wrapped it.
        utils_chaos: The module whose `_move_and_click` the capture taps through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        utils = loaded("utils")
        if utils is None or type(task).__name__ != SORTIE_MODE or task.node_status.get(READ):
            return handler(task)
        original = utils_chaos._move_and_click

        def closing(task_, x, y):
            if (x, y) == PAGE_CLOSE and not task_.node_status.get(READ):
                task_.node_status[READ] = True
                # The team read after the capture takes its names from the Combatants pass, which the deck read replaces.
                texts = task_.all_texts
                read_deck(task_, utils)
                task_.all_texts = texts
            return original(task_, x, y)

        with standing_in(utils_chaos, _move_and_click=closing):
            return handler(task)

    return wrapped


def apply():
    """Read the deck on Sortie's information page trip, just before the page closes."""
    global _patched
    if _patched:
        return

    def install():
        utils_chaos = loaded("utils_chaos")
        if utils_chaos is not None:
            wrap(utils_chaos, "handle_archive_target_member", lambda handler: reading_the_deck(handler, utils_chaos), TAG)

    register(install)
    _patched = True
