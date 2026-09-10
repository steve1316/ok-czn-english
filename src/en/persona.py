"""Let the Season 3 Persona card screen see its own cards on the Global client.

`handle_mask_card` offers three Persona cards and picks one. It finds them by testing each recognised card's
name for the Chinese literal 人格面具, and on this client the reader returns English names, so that list comes
back empty every time. The handler reads an empty list as "a Persona has already been chosen", presses Skip,
and returns True - which means the screen has never once been played on the Global client, quietly, since the
season shipped. Nothing in a log says so; the run simply moves on.

The reverse OCR catalog cannot fix this one. Every other Chinese literal it rewrites is a caption - a title, a
button, a prompt - but this is tested against a card *name*, and names are what the user's own priority lists
are matched against. Rewriting them would fix the filter and break every list at the same time.

So the marker is added rather than substituted, and only for the length of one call: a Persona's name is
handed to upstream as `人格面具Persona of Loss`, which satisfies the filter while leaving the English name
inside it for the priority match that follows. Ordinary cards are untouched, and so is a Chinese client, where
the literal is already there.
"""

from ok import Logger

from src.en.handlers import loaded, register, standing_in, wrap

logger = Logger.get_logger(__name__)

# The literal `handle_mask_card` tests every card name for.
MASK = "人格面具"
# What the client calls the same cards. Every Persona name in the client's own table contains it.
ENGLISH = "Persona"
# Names this change in the shared record of what a function already carries.
TAG = "persona names"

_patched = False


def marked(cards):
    """Add the literal upstream's filter looks for to any Persona card's name.

    Args:
        cards: The cards the recognizer found.

    Returns:
        The same cards, with Persona names marked.
    """
    for card in cards:
        name = card.get("name") or ""
        if ENGLISH in name and MASK not in name:
            card["name"] = f"{MASK}{name}"
    return cards


def marking_personas(handler, module):
    """Wrap `handle_mask_card` so it can recognise an English Persona card.

    Args:
        handler: The handler to wrap, upstream's or another patch's.
        module: The module holding the `recognize_cards` the handler resolves through.

    Returns:
        The wrapped handler.
    """
    def wrapped(task):
        original = module.recognize_cards

        def recognised(*args, **kwargs):
            return marked(original(*args, **kwargs))

        with standing_in(module, recognize_cards=recognised):
            return handler(task)

    return wrapped


def install(utils):
    """Mark Persona names for the handler that picks one.

    The names are marked on `utils_chaos` rather than on `utils`, because Chaos does
    `from utils import recognize_cards` and so resolves the call through its own name. Patching the module
    the function was defined in would change nothing.

    Args:
        utils: The loaded `utils` module, or None when it is not importable yet.
    """
    if utils is None:
        return
    utils_chaos = loaded("utils_chaos")
    if utils_chaos is None:
        return
    wrap(utils_chaos, "handle_mask_card", lambda handler: marking_personas(handler, utils_chaos), TAG)


def apply():
    """Stop the Persona card screen skipping itself on the Global client."""
    global _patched
    if _patched:
        return
    register(lambda: install(loaded("utils")))
    _patched = True
