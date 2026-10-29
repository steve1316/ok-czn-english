"""Move the real cursor out of the bot's way while it sits over the game window.

Upstream posts clicks and keys straight to the game window, which works with the game behind other windows. The game follows the real
mouse instead whenever it is over the window, so a click lands wherever the player's cursor is, and a card the cursor rests on stays hovered
and refuses every card key. A click now borrows the cursor and puts it back, and a key parks it in an empty strip of the screen.
"""

import ctypes
import time

import pywintypes
import win32api
import win32con
import win32gui

from ok import Logger

logger = Logger.get_logger(__name__)

# Where a key press parks the cursor, as a share of the frame: the empty strip above the battlefield. Clear of the hand, the buttons and the
# enemies, since hovering an enemy can move the target a raised card goes to.
PARK = (0.55, 0.08)
# How long the cursor stays on a click before it goes back, so the game reads the press there and not at the player's cursor. ~3 frames.
HOLD = 0.05

_patched = False


def over_game(interaction):
    """Find the real cursor when it is over an uncovered part of the game window, where the game reads it instead of posted input.

    Args:
        interaction: The running `PostMessageInteraction`, whose `hwnd_window` holds the game's window handles.

    Returns:
        The cursor's screen position, or None when it is elsewhere or cannot be read, as on the lock screen.
    """
    window = interaction.hwnd_window
    try:
        at = win32api.GetCursorPos()
        under = win32gui.WindowFromPoint(at)
        game = {win32gui.GetAncestor(hwnd, win32con.GA_ROOT) for hwnd in (window.hwnd, window.top_hwnd) if hwnd}
        return at if under and win32gui.GetAncestor(under, win32con.GA_ROOT) in game else None
    except pywintypes.error:
        return None


def screen_point(interaction, x, y):
    """Turn a frame position into the screen position upstream's PostMessage click aims at.

    Args:
        interaction: The running `PostMessageInteraction`.
        x: The frame x in pixels, as `click` receives it.
        y: The frame y in pixels.

    Returns:
        The screen position.
    """
    window = interaction.hwnd_window
    x, y = window.get_top_window_cords(x, y)
    return win32gui.ClientToScreen(window.top_hwnd or window.hwnd, (int(x), int(y)))


def move_cursor(point):
    """Put the real cursor on a screen position, giving up quietly when Windows refuses.

    Args:
        point: The screen position.

    Returns:
        True when the cursor moved.
    """
    try:
        win32api.SetCursorPos(point)
        return True
    except pywintypes.error:
        return False


def freeze(frozen):
    """Freeze or release the player's mouse and keyboard.

    Windows only allows it from an elevated process. The app runs as Administrator for the elevated game, and without that nothing freezes.

    Args:
        frozen: True to freeze, False to release.
    """
    ctypes.windll.user32.BlockInput(frozen)


def borrowing_cursor(original):
    """Wrap `PostMessageInteraction.click` so a click with the cursor over the game moves it onto the target and back.

    Args:
        original: Upstream's `click`.

    Returns:
        The wrapped method.
    """
    def click(self, x=-1, y=-1, *args, **kwargs):
        # -1 repeats the last position, which upstream tracks itself.
        was = over_game(self) if x >= 0 and y >= 0 else None
        if was is None:
            return original(self, x, y, *args, **kwargs)
        # Frozen so the player's hand cannot push the cursor off the target before the press lands.
        freeze(True)
        moved = False
        try:
            moved = move_cursor(screen_point(self, x, y))
            if moved:
                logger.debug(f"the cursor is over the game, so it moves from {was} onto the click at ({x}, {y}) and back")
            return original(self, x, y, *args, **kwargs)
        finally:
            if moved:
                time.sleep(HOLD)
                move_cursor(was)
            freeze(False)

    return click


def parking_cursor(original):
    """Wrap `PostMessageInteraction.send_key` so a key with the cursor over the game first parks it at `PARK`.

    It stays parked: put back on the hand, it would hover a card again before the Enter that confirms the one a key raised.

    Args:
        original: Upstream's `send_key`.

    Returns:
        The wrapped method.
    """
    def send_key(self, key, *args, **kwargs):
        if over_game(self) is not None:
            logger.debug(f"the cursor is over the game, so it is parked clear of the hand before key {key}")
            move_cursor(screen_point(self, PARK[0] * self.capture.width, PARK[1] * self.capture.height))
        return original(self, key, *args, **kwargs)

    return send_key


def apply():
    """Keep the real cursor from overriding the bot's clicks and keys while it is over the game."""
    global _patched
    if _patched:
        return
    from ok.device.interaction import PostMessageInteraction

    PostMessageInteraction.click = borrowing_cursor(PostMessageInteraction.click)
    PostMessageInteraction.send_key = parking_cursor(PostMessageInteraction.send_key)
    _patched = True
    logger.info("clicks and keys move the real cursor out of the way while it is over the game")
