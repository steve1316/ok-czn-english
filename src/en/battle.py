"""Play a Sortie battle from what the cards do, instead of pressing every hotkey and hoping.

Upstream's `handle_battle_page` plays the first hand card that matches the user's Play Priority list. When
nothing matches - which on the Global client is every turn, since that list starts empty - it falls through
to `_try_all_card_keys`, which presses each hotkey from the hand size down to one at about a second and a
half a press. At nine cards that is thirteen seconds of blind input per turn, and whatever it plays is
whatever happened to be under the last key that worked.

That fallback is the only thing replaced here. Upstream keeps the frame: the Ego check, the end-of-turn
button, the stuck detection, the final-boss flag. A card the user's Play Priority list names is still played
by upstream, unchanged, so a tuned list keeps behaving as it did.

`_try_all_card_keys` has two callers, though, and rebinding it takes over both. One is the fallback proper,
reached when the list matched nothing. The other is the escape hatch upstream reaches for after a card the
list *did* name has failed to play three times running - and taking that one over is wanted rather than
tolerated, because a card that will not play three times is usually one there are no Action Points for, and
choosing a different card is a better answer than flailing at every key.

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
# `_last_attempted_card`. One attribute, so starting a fresh turn is one assignment rather than three that
# have to agree. The prefix keeps it clear of anything upstream owns.
TURN = "_en_turn"
# Remembers one frame's hand reading, keyed on the OCR pass it came from. `SortieMode.run` builds a fresh
# `all_texts` list every frame, so identity tells frames apart, and a matching list can only ever produce a
# matching hand. Upstream reads the hand twice a frame already; this makes all of those one reading.
HAND_CACHE = "_en_hand_for"

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


class Turn:
    """What one turn has learnt: the hand it last saw, the card it tried, and what the game would not play."""

    def __init__(self, hand_count):
        """Start a turn that has learnt nothing yet.

        Args:
            hand_count: The hand size this turn opened with.
        """
        self.hand_count = hand_count
        self.attempted = None
        self.refused = set()


def turn_of(task, hand_count):
    """Bring the per-turn bookkeeping up to date and hand it back.

    Args:
        task: The running task, which the state is parked on.
        hand_count: The hand size read this frame.

    Returns:
        The `Turn` in progress, fresh when the hand has just been dealt again.
    """
    turn = getattr(task, TURN, None)
    if turn is None or new_turn(turn.hand_count, hand_count):
        turn = Turn(hand_count)
        setattr(task, TURN, turn)
    turn.hand_count = hand_count
    return turn


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
    read_names = utils_sortie._hand_card_names

    def _hand_card_names(task):
        """Read the hand's card names once per OCR pass rather than once per caller.

        Upstream calls this twice a frame - directly, and again inside `_hand_cards` - and the picker would
        have made it three. Each call walks `all_texts` and logs a line for every box on screen, which on a
        battle screen is the noisiest thing the bot does.

        Args:
            task: The running task.

        Returns:
            The name boxes, from this frame's reading or the one already taken from the same OCR pass.
        """
        read_for, names = getattr(task, HAND_CACHE, (None, None))
        if read_for is task.all_texts:
            return names
        names = read_names(task)
        setattr(task, HAND_CACHE, (task.all_texts, names))
        return names

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
        turn = turn_of(task, len(names))

        if was_refused(turn.attempted, names):
            turn.refused.add(turn.attempted)
            task.log_info(f"the game would not play {turn.attempted}, leaving it for the rest of this turn")

        board = cards.Board()
        card = choose(hand, board, turn.refused)
        if card is None:
            if not names:
                # Upstream ends an empty hand itself, so there is nothing here to do and nothing to say.
                return
            task.log_info(f"nothing left worth playing in {names}, ending the turn")
            turn.attempted = None
            task.send_key(END_TURN_KEY)
            task.sleep(AFTER_KEY)
            return

        name = card["name"]
        task.log_info(f"playing {name} for {cards.cost(name)} AP on key {card['key']}, "
                      f"worth {cards.value(name, board):.0f}")
        turn.attempted = name
        task.send_key(card["key"])
        task.sleep(AFTER_KEY)
        task.send_key(CONFIRM_KEY)
        task.sleep(AFTER_CONFIRM)

    # Marked so a later task load recognises the replacement and does not wrap it in itself.
    _try_all_card_keys._en_picker = True
    utils_sortie._try_all_card_keys = _try_all_card_keys
    utils_sortie._hand_card_names = _hand_card_names
    logger.info("sortie battles now pick a card instead of pressing every key")


def apply():
    """Have the card picker stand in for upstream's fallback, once the modes have been imported."""
    global _patched
    if _patched:
        return
    register(install)
    _patched = True
