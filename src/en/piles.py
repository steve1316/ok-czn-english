"""Read the deck off the All Piles view once a Sortie layer, and follow every card gained, removed, copied or sparked after it.

A card in hand shows only its name, and the data holds a card's base text beside every Epiphany it could take, so the picker valued an
Epiphany card by its base text. Upstream never opens the view. This reads it on the information page trip that reads the team.
"""

import difflib
import re
import time
from collections import Counter
from typing import NamedTuple

from ok import Logger

from src.en import cards, quality
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
# What tapping a card does to the deck on each screen upstream picks cards on: the module holding the function, which it also reads the
# cards through, the function, the change, and the column a pick is tapped in when that is not on the card. `select_card` serves several
# screens, so its action decides. Card Assign reads one card and picks it by tapping the combatant who takes it.
GAINED, REMOVED, SPARKED, EPIPHANY = "gained", "removed", "chosen for an Epiphany", "took an Epiphany"
FOLLOWED = (("utils_sortie", "handle_get_card", GAINED, None), ("utils", "handle_card_reward", GAINED, None),
            ("utils", "handle_copy_card_choice", GAINED, None), ("utils", "handle_view_original", EPIPHANY, None), ("utils", "select_card", None, None),
            ("utils", "handle_card_assign", GAINED, 0.756))
SELECT_ACTIONS = {"移除": REMOVED, "复制": GAINED, "闪光": SPARKED, "灵光": SPARKED}
READERS = ("recognize_cards", "recognize_cards_in_deck")
FOLLOW_TAG = "follows the deck"
# Seconds within which the same screen offering the same cards again, and the same card tapped, means its last pick did not take. Live, an
# Obtain Card pick came back 2.3s later and an Epiphany pick 1.1s later, each counted twice. Two Claims on one reward screen were 6s apart.
RETRY_SECONDS = 5

_patched = False
# The version each card chosen for an Epiphany had, by canonical name, until the next screen picks the one it takes instead.
_sparking = {}
_last_pick = None


class Pick(NamedTuple):
    """The deck changes one visit to a screen made, kept until the next visit says whether they took."""

    # The wrapped function of the screen, so a visit to another screen is never taken for a retry.
    handler: object
    # The canonical name of each card the screen read, None where OCR spelled one past recognising.
    offer: list
    # `time.monotonic()` at the first pick of the visit.
    at: float
    # A token for the visit, so the second tap of one visit is not taken for a retry of the first.
    visit: object
    # The `(name, version, by)` changes the visit made to the deck, in order.
    changes: list


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
        Canonical card name to a `Counter` of the version texts its copies matched. Pages overlap, so a version counts the most copies
        of it any one page showed, which can miss a copy two rows away.
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
        for (name, version), number in Counter((name, version_of(name, text)) for name, text, _ in page).items():
            held = copies.setdefault(name, Counter())
            held[version] = max(held[version], number)
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
    epiphanies = sorted(name for name, texts in copies.items() if set(texts) - {DESCRIPTIONS.get(name)})
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


def follow(change, card):
    """Change the deck by one card tapped on a screen that changes it.

    Args:
        change: What the tap does, one of `GAINED`, `REMOVED`, `SPARKED` and `EPIPHANY`.
        card: The card tapped, as upstream's reader returned it, with its `name` and `description`.

    Returns:
        The `(name, version, by)` changes made to the deck, so a pick that did not take can be undone.
    """
    name = quality.CARD_INDEX.look_up(card.get("name") or "")
    if name not in cards.CARD_COST:
        logger.debug(f"tapped {card.get('name')!r} but it names no card, so the deck is left as it was")
        return []
    version = version_of(name, card.get("description") or "")
    if change == SPARKED:
        _sparking[name] = version
        return []
    changes = [(name, _sparking.pop(name, DESCRIPTIONS.get(name) or ""), -1)] if change == EPIPHANY else []
    changes.append((name, version, -1 if change == REMOVED else 1))
    for changed in changes:
        cards.change_deck(*changed)
    logger.info(f"{name} {change}, {'its base' if version == DESCRIPTIONS.get(name) else 'an Epiphany'}: {version!r}")
    return changes


def offered_again(before, now):
    """Say whether a screen offers the cards it offered on the last visit, wherever they now sit.

    Args:
        before: The canonical names the last visit read, None where OCR spelled one past recognising.
        now: The same for this visit.

    Returns:
        True when the count matches and every name this visit recognised was on offer last time.
    """
    return len(before) == len(now) and all(name in before for name in now if name)


def following(handler, module, change, column=None):
    """Wrap a function that taps cards on a screen, so each card it taps changes the deck.

    Args:
        handler: The function to wrap, upstream's or another patch's.
        module: The module the function reads the cards through.
        change: What a tap does, or None to take it from the `action` upstream passes `select_card`.
        column: The screen x a pick is tapped at when it is not on the card, which picks the one card read. None to match the card's point.

    Returns:
        The wrapped function.
    """
    def wrapped(task, *args, **kwargs):
        kind = change or SELECT_ACTIONS.get(kwargs.get("action", ""))
        if kind is None or type(task).__name__ != SORTIE_MODE:
            return handler(task, *args, **kwargs)
        shown, offer, visit = [], [], object()

        def reading(recognise):
            def recognised(*args_, **kwargs_):
                found = recognise(*args_, **kwargs_)
                shown[:] = found or []
                offer[:] = [quality.CARD_INDEX.look_up(card.get("name") or "") for card in shown]
                return found
            return recognised

        click = task.click

        # Upstream taps a card at the very point its reader returned, so matching the point finds the card.
        def clicked(x=-1, y=-1, *args_, **kwargs_):
            global _last_pick
            result = click(x, y, *args_, **kwargs_)
            card = next((card for card in shown if (card.get("x"), card.get("y")) == (x, y)), None)
            if card is None and column is not None and x == column and len(shown) == 1:
                card = shown[0]
            if card is None:
                return result
            shown.remove(card)
            last, now = _last_pick, time.monotonic()
            if last is None or last.visit is not visit:
                # A second pick off the same offer takes another card. Live, Gear Bag 2.3s after Photo Time undid Photo Time, though both took.
                again = quality.CARD_INDEX.look_up(card.get("name") or "") in {name for name, *_ in last.changes} if last else False
                if again and last.handler is handler and now - last.at < RETRY_SECONDS and offered_again(last.offer, offer):
                    logger.info(f"the same {len(offer)} card(s) are on offer again, so the last pick did not take and is undone")
                    for name, version, by in reversed(last.changes):
                        cards.change_deck(name, version, -by)
                _last_pick = Pick(handler, list(offer), now, visit, [])
            _last_pick.changes.extend(follow(kind, card))
            return result

        readers = {name: reading(getattr(module, name)) for name in READERS if name in vars(module)}
        with standing_in(module, **readers), standing_in(task, click=clicked):
            return handler(task, *args, **kwargs)

    return wrapped


def apply():
    """Read the deck on Sortie's information page trip, just before the page closes, and follow each change to it after."""
    global _patched
    if _patched:
        return

    def install():
        utils_chaos = loaded("utils_chaos")
        if utils_chaos is not None:
            wrap(utils_chaos, "handle_archive_target_member", lambda handler: reading_the_deck(handler, utils_chaos), TAG)
        for module_name, name, change, column in FOLLOWED:
            module = loaded(module_name)
            if module is not None:
                wrap(module, name, lambda handler, module=module, change=change, column=column: following(handler, module, change, column), FOLLOW_TAG)

    register(install)
    _patched = True
