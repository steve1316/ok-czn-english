"""Meditate at a Safe Zone to re-roll the Epiphany on a card the build preset pinned, and nowhere else.

Upstream meditates on the cards in its own list once Credits pass a threshold, whatever shape the party is in, and Sortie never meditates.
On the Global client the reconstruct screen pins every card whose Epiphany the build preset does not want, so the pin is the target.
"""

import time

import numpy as np

from ok import Logger

from src.en.handlers import insert_before, loaded, register, standing_in, wrap
from src.en.reobserve import number_in
from src.en.rest import interactions_left
from src.en.screen import colour_share, frame_of, patch_of, text_in_region

logger = Logger.get_logger(__name__)

# The switch, added fork-side under the shop switch both modes declare. Off, the run never meditates.
MEDITATE = "Meditate on Pinned Cards"
# The party has to be this healthy, in percent, before a Safe Zone's interaction goes on Meditation rather than Rest.
MIN_HP_PERCENT = 95
# The most Stress any combatant may carry, as a share of their bar. Rest is what lowers it.
MAX_STRESS = 0.25
# The Safe Zone's Meditation option, and where its label and price sit. The price read 80 at 1080p.
MEDITATION = "Meditation"
MEDITATION_REGION = (0.70, 0.52, 0.95, 0.70)
# Upstream's template for the option's praying-hands icon, and where `handle_rest` searches for it.
MEDITATE_ICON = "meditate"
MEDITATE_ICON_REGION = (0.671, 0.433, 0.945, 0.801)
# The strip each combatant's Stress bar runs along under the party's HP bar, one per slot. Measured at 1080p: a purple fill from the bar's
# left end over a grey track (V 77, S 20) about 128px long, at y 66-76.
STRESS_BARS = ((0.070, 0.064, 0.148, 0.069), (0.196, 0.064, 0.274, 0.069), (0.321, 0.064, 0.399, 0.069))
STRESS_LOW = np.array((130, 120, 150), dtype=np.uint8)
STRESS_HIGH = np.array((160, 255, 255), dtype=np.uint8)
TRACK_LOW = np.array((0, 0, 60), dtype=np.uint8)
TRACK_HIGH = np.array((180, 40, 100), dtype=np.uint8)
# How much of a slot's strip the fill and track together have to cover to count as a bar. A real bar covers ~0.85 of it.
MIN_BAR_SHARE = 0.4
# The popup Meditation opens, its caption, and its buttons as `ocr.po` rewrites them.
POPUP = "reconstruct the Epiphany"
POPUP_REGION = (0.05, 0.38, 0.95, 0.50)
CONFIRM, CANCEL = "确认", "取消"
POPUP_BUTTONS = (0.15, 0.6, 0.85, 0.75)
# The card screen that follows, captioned "Select 1 card to spark an Epiphany again.". `ocr_text` rewrites the whole caption to `PICK`
# so upstream's Epiphany picker never answers it, and a caption OCR split round its count still carries the English tail.
PICK = "冥想重构卡牌"
PICK_TAIL = "an Epiphany again"
PICK_CAPTION = (0.08, 0.0, 0.65, 0.09)
# The screen's buttons along the bottom right: Cancel, and "Epiphany Again" which `ocr.po` rewrites to upstream's literal.
PICK_CANCEL = (0.62, 0.88, 0.81, 0.98)
EPIPHANY_AGAIN = "重新闪光"
EPIPHANY_AGAIN_POINT = (0.945, 0.918)
# Upstream's card page scroll, as `select_card` uses it: the scrollbar it measures, the point that turns white at the bottom, and where it
# scrolls. A share of white below `SINGLE_PAGE` means there is no scrollbar, so the one page is everything.
SCROLLBAR = (0.976, 0.119, 0.988, 0.858)
SINGLE_PAGE = 0.01
BOTTOM_POINT = (0.982, 0.846)
SCROLL_POINT = (0.251, 0.735)
MAX_SCROLLS = 20
# How long a decision holds. A Safe Zone visit takes seconds, and the next one is a fight or more away.
HOLD_SECONDS = 60
# Task attributes: the visit's decision as a `(meditating, stamp)` pair, and how far the card page was scrolled.
DECISION = "_en_meditation"
SCROLLS = "_en_meditation_scrolls"
# Tag for this change in `wrap`'s record.
UPSTREAM_TAG = "meditation left to the fork"
# The handlers each new one runs ahead of. Every mode list holds them.
SAFE_ZONE_ANCHORS = ("handle_rest", "handle_rest_sortie")
POPUP_ANCHOR = "handle_center_confirm"
PICK_ANCHOR = "handle_reflash"

_patched = False


def decide(task, meditating):
    """Stamp this visit's decision on the task.

    Args:
        task: The running task.
        meditating: True when Meditation was chosen, False when it was turned down for want of a pinned card.
    """
    setattr(task, DECISION, (meditating, time.monotonic()))


def decision(task):
    """Read this visit's decision, if it is recent enough to still stand.

    Args:
        task: The running task.

    Returns:
        What `decide` stamped within `HOLD_SECONDS`, or None when nothing was decided.
    """
    meditating, stamped = getattr(task, DECISION, (None, None))
    return meditating if stamped is not None and time.monotonic() - stamped < HOLD_SECONDS else None


def stress_levels(task):
    """Read how full each combatant's Stress bar is.

    Args:
        task: The running task, whose frame shows the party bar along the top.

    Returns:
        One share from 0 to 1 per bar found, in slot order. A slot with no bar is left out.
    """
    frame = frame_of(task)
    levels = []
    for region in STRESS_BARS:
        patch = patch_of(frame, region)
        filled, track = colour_share(patch, STRESS_LOW, STRESS_HIGH), colour_share(patch, TRACK_LOW, TRACK_HIGH)
        if filled + track >= MIN_BAR_SHARE:
            levels.append(filled / (filled + track))
    return levels


def why_not(task, utils):
    """Give the reason a Safe Zone's interaction should not go on Meditation.

    Args:
        task: The running task, on a Safe Zone screen.
        utils: Upstream's `utils` module, for its HP and Credit readers.

    Returns:
        The reason, or None when the party is fit to meditate.
    """
    hp = utils._get_current_hp_percent(task)
    if hp is False:
        return "HP was unread"
    if hp < MIN_HP_PERCENT:
        return f"HP is {hp}%, under {MIN_HP_PERCENT}%"
    price, credits = number_in(task, MEDITATION_REGION), utils._get_current_credit(task)
    if price is None or credits < price:
        return f"Meditation costs {price} and the run holds {credits} Credits"
    stress = stress_levels(task)
    if not stress:
        return "no Stress bar was read"
    if max(stress) >= MAX_STRESS:
        return f"Stress reads {[round(level, 2) for level in stress]}, at or over {MAX_STRESS}"
    return None


def safe_zone_handler(utils):
    """Build the handler that picks Meditation over Rest when the party is healthy and calm.

    Args:
        utils: Upstream's `utils` module.

    Returns:
        The handler.
    """
    def handle_meditation(task):
        # The count is the cheap proof this is a Safe Zone with an interaction going spare, and keeps the reads below off battle frames.
        if not interactions_left(task) or decision(task) is not None or not utils._get_config_value(task, MEDITATE, True):
            return False
        label = text_in_region(task, MEDITATION, MEDITATION_REGION)
        if label is None:
            return False
        reason = why_not(task, utils)
        if reason:
            logger.debug(f"Meditation passed over, since {reason}")
            return False
        icon = task.find_one(feature_name=MEDITATE_ICON, box=task.box_of_screen(*MEDITATE_ICON_REGION))
        task.log_info("party is healthy and calm, so meditating to re-roll a pinned card's Epiphany")
        decide(task, True)
        setattr(task, SCROLLS, 0)
        task.click_box(icon or label)
        task.sleep(1)
        return True

    return handle_meditation


def handle_meditation_popup(task):
    """Answer the Meditation popup: Confirm when the fork chose it, Cancel when it was turned down or never chosen.

    Upstream's centre Confirm would otherwise press Confirm every time, and walk straight back into the card screen just cancelled.

    Args:
        task: The running task, whose `all_texts` is the current screen.

    Returns:
        True when this frame was claimed.
    """
    if text_in_region(task, POPUP, POPUP_REGION) is None:
        return False
    go = decision(task) is True
    button = text_in_region(task, CONFIRM if go else CANCEL, POPUP_BUTTONS)
    if button is None:
        return False
    task.log_info("confirming Meditation" if go else "Meditation was not chosen, so cancelling it")
    task.click_box(button)
    task.sleep(1)
    return True


def pick_handler(utils):
    """Build the handler for the card screen, which takes the first pinned card and otherwise backs out to Rest.

    Args:
        utils: Upstream's `utils` module.

    Returns:
        The handler.
    """
    def handle_meditation_pick(task):
        if all(text_in_region(task, caption, PICK_CAPTION) is None for caption in (PICK, PICK_TAIL)):
            return False
        again = utils.find_box_at_point(task, *EPIPHANY_AGAIN_POINT)
        if again is not None and EPIPHANY_AGAIN in again.name and utils.is_button_active(task, again):
            # A card is already chosen. Upstream's handler presses the button.
            return False
        cards = utils.recognize_cards_in_deck(task, page="meditation")
        pinned = [card for card in cards if card.get("pinned")]
        if pinned:
            card = pinned[0]
            task.log_info(f"{card['name']} is pinned, so its Epiphany is re-rolled")
            utils._move_and_click(task, card["x"], card["y"])
            return True
        scrolls = getattr(task, SCROLLS, 0)
        more = (scrolls < MAX_SCROLLS and utils.region_white_ratio(task, SCROLLBAR) >= SINGLE_PAGE
                and not utils._point_is_white(task, *BOTTOM_POINT, "meditation"))
        if more:
            setattr(task, SCROLLS, scrolls + 1)
            utils._scroll_card_page(task, *SCROLL_POINT, -3, "meditation")
            return True
        cancel = text_in_region(task, CANCEL, PICK_CANCEL)
        if cancel is None:
            return False
        task.log_info(f"no pinned card among {[card['name'] for card in cards]}, so resting instead")
        decide(task, False)
        task.click_box(cancel)
        task.sleep(1)
        return True

    return handle_meditation_pick


def without_upstream_meditation(handler, utils):
    """Wrap upstream's Chaos rest handler so its own list never sends the run to meditate.

    It reads the cards still owed a Meditation out of the deck state, so the wrapper hides that one entry for the length of the call.

    Args:
        handler: Upstream's `handle_rest`, or another patch's wrapper of it.
        utils: Upstream's `utils` module, whose `_member_deck_state` the handler reads.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original = utils._member_deck_state

        def without_meditation(task_):
            return {key: value for key, value in original(task_).items() if key != "冥想"}

        with standing_in(utils, _member_deck_state=without_meditation):
            return handler(task)

    return wrapped


def install(utils):
    """Take Meditation off upstream's list and give it to the fork's three handlers.

    Args:
        utils: Upstream's `utils` module, or None when it has not been imported yet.
    """
    if utils is None:
        return
    wrap(utils, "handle_rest", lambda handler: without_upstream_meditation(handler, utils), UPSTREAM_TAG)
    for anchor in SAFE_ZONE_ANCHORS:
        insert_before(anchor, safe_zone_handler(utils))
    insert_before(POPUP_ANCHOR, handle_meditation_popup)
    insert_before(PICK_ANCHOR, pick_handler(utils))


def apply():
    """Meditate on a pinned card's Epiphany when the party can spare the Rest."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
