"""Play a Sortie battle from what the cards do, instead of pressing every hotkey and hoping.

Upstream's `handle_battle_page` plays the first hand card that matches the user's Play Priority list. When
nothing matches - which on the Global client is every turn, since that list starts empty - it falls through
to `_try_all_card_keys`, which presses each hotkey from the hand size down to one at about a second and a
half a press. At nine cards that is thirteen seconds of blind input per turn, and whatever it plays is
whatever happened to be under the last key that worked.

That fallback is the only thing replaced here. Upstream keeps the frame: the Ego check, the end-of-turn
button, the stuck detection, the final-boss flag. The user's Play Priority list keeps winning outright, so
anyone who has tuned one sees no change at all. What changes is what happens when the list has nothing to
say, which is where `cards.py` now decides instead of the keyboard.

**Action Points are not read.** The position of that readout has not been confirmed against a frame with a
hand in it, and guessing wrong would end turns early, so the budget is assumed rather than read. That costs
less than it sounds: the game itself refuses a card there is no room for, and a card that is still in hand
after being tried is recorded as refused for the rest of the turn and passed over. The turn corrects itself
against the game rather than against a number this module believes in.
"""

from ok import Logger

from src.en import cards
from src.en.handlers import loaded, register
from src.en.overrides import SMART_CARD_PLAY

logger = Logger.get_logger(__name__)

# Parked on the task for the length of a battle, the way upstream parks `_play_stuck_count` and
# `_last_attempted_card`. The prefix keeps them clear of anything upstream owns.
REFUSED = "_en_refused_cards"
ATTEMPTED = "_en_attempted_card"
LAST_HAND = "_en_last_hand_count"

# Upstream's own timings for playing a card, kept so the two paths feel the same to the game.
AFTER_KEY = 1
AFTER_CONFIRM = 2
# The key that ends a turn, as upstream sends it.
END_TURN_KEY = "e"
CONFIRM_KEY = "enter"

_patched = False


def choose(hand, board, refused):
    """Pick the card to play next, or nothing when the turn is done.

    Args:
        hand: Hand cards as `_hand_cards` reads them.
        board: The `cards.Board` to decide against.
        refused: Names the game has already declined to play this turn.

    Returns:
        The hand card to play, or None when nothing is left worth playing.
    """
    playable = [card for card in hand if card.get("key") and card["name"] not in refused]
    chosen = cards.plan(playable, board)
    return chosen[0] if chosen else None


def was_refused(attempted, hand_names):
    """Say whether the card tried last frame is still sitting in hand.

    Counting the hand does not answer this. A card that draws replaces itself, so the count can be unchanged
    on a card that played perfectly well. Whether that particular card is still there does answer it.

    Args:
        attempted: The card name tried last frame, or None when nothing was.
        hand_names: The names now in hand.

    Returns:
        True when the game would not play it, so it should be passed over for the rest of the turn.
    """
    return attempted is not None and attempted in hand_names


def new_turn(before, after):
    """Say whether the hand has been dealt again since the last frame.

    Args:
        before: The hand size last frame, or None on the first frame of a battle.
        after: The hand size now.

    Returns:
        True when a fresh turn has started, so what the last turn refused no longer applies.
    """
    return before is None or after > before


def state_of(task, hand_count):
    """Bring the per-turn bookkeeping up to date and hand back what this frame should avoid.

    Args:
        task: The running task, which the state is parked on.
        hand_count: The hand size read this frame.

    Returns:
        The set of card names already refused this turn.
    """
    if new_turn(getattr(task, LAST_HAND, None), hand_count):
        setattr(task, REFUSED, set())
        setattr(task, ATTEMPTED, None)
    setattr(task, LAST_HAND, hand_count)
    return getattr(task, REFUSED, set())


def install():
    """Put the card picker in place of upstream's press-every-key fallback.

    `handle_battle_page` reaches `_try_all_card_keys` as a module global, which Python resolves when the call
    is made, so rebinding it on the module is enough. That leaves every other line of upstream's battle frame
    running exactly as it did.

    Runs once per task load, so it has to be safe to call again: a replacement already in place is left alone
    rather than wrapped in a second one.
    """
    utils = loaded("utils")
    utils_sortie = loaded("utils_sortie")
    if utils is None or utils_sortie is None:
        return
    if getattr(utils_sortie._try_all_card_keys, "_en_picker", False):
        return
    blind_fallback = utils_sortie._try_all_card_keys

    def _try_all_card_keys(task, count):
        """Play the best card in hand, in place of pressing every key in turn.

        Args:
            task: The running task.
            count: The hand size upstream read, kept for the signature this is called with.
        """
        if not utils._get_config_value(task, SMART_CARD_PLAY, True):
            blind_fallback(task, count)
            return

        hand = utils_sortie._hand_cards(task) or []
        names = [card["name"] for card in hand]
        refused = state_of(task, len(names))

        attempted = getattr(task, ATTEMPTED, None)
        if was_refused(attempted, names):
            refused.add(attempted)
            task.log_info(f"the game would not play {attempted}, leaving it for the rest of this turn")

        board = cards.Board()
        card = choose(hand, board, refused)
        if card is None:
            if not names:
                # Upstream ends an empty hand itself, so there is nothing here to do and nothing to say.
                return
            task.log_info(f"nothing left worth playing in {names}, ending the turn")
            setattr(task, ATTEMPTED, None)
            task.send_key(END_TURN_KEY)
            task.sleep(AFTER_KEY)
            return

        name = card["name"]
        task.log_info(f"playing {name} for {cards.cost(name)} AP on key {card['key']}, "
                      f"worth {cards.value(name, board):.0f}")
        setattr(task, ATTEMPTED, name)
        task.send_key(card["key"])
        task.sleep(AFTER_KEY)
        task.send_key(CONFIRM_KEY)
        task.sleep(AFTER_CONFIRM)

    # Marked so a later task load recognises the replacement and does not wrap it in itself.
    _try_all_card_keys._en_picker = True
    utils_sortie._try_all_card_keys = _try_all_card_keys
    logger.info("sortie battles now pick a card instead of pressing every key")


def apply():
    """Have the card picker stand in for upstream's fallback, once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
