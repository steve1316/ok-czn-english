"""Take the card the user's build preset pinned, wherever a card screen offers one.

A build preset marks the cards a combatant's build wants, and the client draws a small orange pin in the
top-right corner of every marked card - on the removal grid, on the Epiphany picker, on the card detail
screen. Nothing in `ok_tasks/` knows about it, because the mark is a Global-client feature, so the pick has
always come down to the priority lists alone.

The pin is read off the frame rather than the OCR pass, since it carries no text. It is anchored on the card's
own type icon, which is the template match the recognizer already builds every card around, so no new template
and no new search are needed - just a small patch of pixels at a fixed offset from a box that is already in
hand. Measured across the captured screens the offset is stable to a pixel or two within a layout, and the two
layouts in use differ enough to need one offset each.

Colour, not shape. The pin is a solid amber disc and everything that can sit behind it - card art, the frame,
the glitter on an Epiphany screen - is either far off that hue or far less saturated. On the worst captured
case, a card buried in white sparkle, the probe still came back two-thirds amber against nothing at all for an
unpinned card beside it, so the threshold has room on both sides.

Marking and narrowing are kept apart on purpose. Every card the recognizers hand back is marked, since that
costs one small patch of pixels and nothing reads the mark unless it wants to. Withholding the unpinned ones
happens only inside the handlers that are about to *choose* a card, because several other callers count what
they were given rather than ranking it - `handle_mask_card` treats fewer than three cards as "the choice has
already been made" - and a narrowed list would quietly change what those counts mean.

Where it does narrow, upstream then ranks what is left with the user's own priority config, exactly as before.
A screen with nothing pinned, or with everything pinned, is handed over untouched: a filter that removes all
of the candidates, or none of them, is not worth applying.
"""

import numpy as np

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap
from src.en.screen import colour_share

logger = Logger.get_logger(__name__)

# Where the pin sits relative to the card's type icon, as (dx, dy) of the screen. The deck grid is used by the
# removal and Epiphany screens; the three-card pick draws larger cards and needs its own.
DECK_OFFSET = (0.0964, -0.0532)
PICK_OFFSET = (0.1411, -0.0713)
# The patch sampled at that point, in pixels. The pin is about 29 across, so this stays well inside it and
# tolerates the pixel or two the offset drifts between screens.
PROBE = 19
# The pin's colour, as inclusive HSV bounds. Amber, saturated and bright. Held as arrays because `inRange`
# would otherwise rebuild them on every card.
PIN_LOW = np.array((5, 150, 150), dtype=np.uint8)
PIN_HIGH = np.array((25, 255, 255), dtype=np.uint8)
# How much of the patch has to be that colour. Measured: about 0.66 on a pin, 0.00 without one.
MIN_ORANGE = 0.25

# The recognizers to mark, and the layout each one reads.
RECOGNIZERS = {
    "recognize_cards": PICK_OFFSET,
    "recognize_cards_in_deck": DECK_OFFSET,
}
# The places a card is actually chosen, and the recognizer each one narrows. `select_card` covers the removal
# and Epiphany grids; the other two are the screens that offer three cards at once.
CHOOSERS = {
    "select_card": "recognize_cards_in_deck",
    "handle_card_reward": "recognize_cards",
    "handle_view_original": "recognize_cards",
}
# Names each change in the shared record of what a function already carries.
MARK_TAG = "pin marks"
NARROW_TAG = "pinned only"

_patched = False


def probe_box(task, feature_box, offset):
    """Work out the patch of frame the pin would occupy for one card.

    Args:
        task: The running task, for the screen's size.
        feature_box: The card's type-icon match, which the offset is measured from.
        offset: The layout's `(dx, dy)`.

    Returns:
        The patch's top-left `(x, y)`, clamped so the whole square stays on the frame.
    """
    center_x = feature_box.x + feature_box.width / 2 + offset[0] * task.width
    center_y = feature_box.y + feature_box.height / 2 + offset[1] * task.height
    return (int(min(max(0, round(center_x - PROBE / 2)), task.width - PROBE)),
            int(min(max(0, round(center_y - PROBE / 2)), task.height - PROBE)))


def is_pinned(task, card, offset):
    """Report whether a card carries the build preset's pin.

    Args:
        task: The running task, whose `frame` holds the current capture.
        card: A card dict from one of the recognizers.
        offset: The layout's `(dx, dy)`.

    Returns:
        True when the pin is there.
    """
    feature_box = card.get("feature_box")
    if task.frame is None or feature_box is None:
        return False
    x, y = probe_box(task, feature_box, offset)
    patch = task.frame[y:y + PROBE, x:x + PROBE, :3]
    return colour_share(patch, PIN_LOW, PIN_HIGH) >= MIN_ORANGE


def marked(task, cards, offset):
    """Record on each card whether the build preset pinned it.

    Args:
        task: The running task.
        cards: The cards the recognizer found.
        offset: The layout's `(dx, dy)`.

    Returns:
        The same cards, each carrying a `pinned` key.
    """
    for card in cards:
        card["pinned"] = is_pinned(task, card, offset)
    return cards


def only_pinned(cards):
    """Narrow a screen's cards to the ones the build preset pinned.

    Args:
        cards: The cards the recognizer found, already marked.

    Returns:
        Just the pinned cards, or every card when the pin cannot separate them.
    """
    pinned = [card for card in cards if card.get("pinned")]
    # Narrowing to all of them, or to none of them, would change nothing but the log.
    if not pinned or len(pinned) == len(cards):
        return cards
    logger.info(f"build preset pinned {[card['name'] for card in pinned]}, so the rest are set aside")
    return pinned


def tagging(recognise, offset):
    """Wrap a card recognizer so every card it returns says whether it is pinned.

    Args:
        recognise: The recognizer to wrap.
        offset: The layout that recognizer reads.

    Returns:
        The wrapped recognizer.
    """
    def wrapped(task, *args, **kwargs):
        return marked(task, recognise(task, *args, **kwargs), offset)

    return wrapped


def narrowing(chooser, utils, recognizer):
    """Wrap a function that picks a card so it only ever sees the pinned candidates.

    Args:
        chooser: The handler or helper about to choose, upstream's or another patch's.
        utils: The module holding the recognizer.
        recognizer: The name of the recognizer to narrow for the length of the call.

    Returns:
        The wrapped function.
    """
    def wrapped(*args, **kwargs):
        original = getattr(utils, recognizer)

        def narrowed(*inner_args, **inner_kwargs):
            return only_pinned(original(*inner_args, **inner_kwargs))

        with standing_in(utils, **{recognizer: narrowed}):
            return chooser(*args, **kwargs)

    return wrapped


def install(utils):
    """Mark every card the recognizers return, and narrow the screens that choose one.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    for name, offset in RECOGNIZERS.items():
        wrap(utils, name, lambda recognise, offset=offset: tagging(recognise, offset), MARK_TAG)
    for name, recognizer in CHOOSERS.items():
        wrap(utils, name,
             lambda chooser, recognizer=recognizer: narrowing(chooser, utils, recognizer), NARROW_TAG)


def apply():
    """Prefer a card the user's build preset pinned on every screen that chooses one."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
