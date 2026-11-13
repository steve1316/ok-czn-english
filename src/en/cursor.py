"""Keep the player's mouse and the bot's input out of each other's way over the game window.

Upstream posts clicks and keys straight to the game window, which works with the game behind other windows. The game follows the real
mouse instead whenever it is over the window, so a click lands wherever the player's cursor is, and a card the cursor rests on stays hovered
and refuses every card key. A click now borrows the cursor and puts it back, and a key parks it in an empty strip of the screen. Input
posted while the player holds the title bar is read as the drag's new position and flings the window, so it waits for the window to be let go.
"""

import ctypes
import time
from ctypes import wintypes

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
# The `GUITHREADINFO` flag Windows sets while a window on the thread is being dragged or resized. A still hold on the title bar takes
# ~1s to set it, but the window holds the mouse capture from the press, so the capture counts too.
GUI_INMOVESIZE = 0x2
# How often held input rechecks whether the player has let go of the game window, in seconds.
WAIT_STEP = 0.1
# How long input waits on a hold before it goes anyway, in seconds, so a capture nobody lets go of cannot hang the bot.
WAIT_LIMIT = 30
# The side mouse buttons' release, which pywin32's `win32con` leaves out.
WM_XBUTTONUP = 0x020C
# Releases never start a drag, and holding them back behind the capture the bot's own press took would wait forever.
RELEASES = frozenset({win32con.WM_LBUTTONUP, win32con.WM_RBUTTONUP, win32con.WM_MBUTTONUP, WM_XBUTTONUP, win32con.WM_KEYUP, win32con.WM_SYSKEYUP})

_patched = False
# Whether `freeze` has the player's input frozen, so the player cannot be holding anything new.
_frozen = False


class GUITHREADINFO(ctypes.Structure):
    """The Win32 struct `GetGUIThreadInfo` fills in. Only `flags` is read."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),  # The struct's own size, which the caller sets.
        ("flags", wintypes.DWORD),  # The thread's state bits, `GUI_INMOVESIZE` among them.
        ("hwndActive", wintypes.HWND),  # The thread's active window.
        ("hwndFocus", wintypes.HWND),  # The window with the keyboard focus.
        ("hwndCapture", wintypes.HWND),  # The window holding the mouse capture.
        ("hwndMenuOwner", wintypes.HWND),  # The window that owns an open menu.
        ("hwndMoveSize", wintypes.HWND),  # The window being moved or sized.
        ("hwndCaret", wintypes.HWND),  # The window showing the caret.
        ("rcCaret", wintypes.RECT),  # The caret's bounds.
    ]


def over_game(interaction):
    """Find the real cursor when it is over an uncovered part of the game's client area, where the game reads it instead of posted input.

    The title bar and borders do not count. Moving the cursor while the player holds the title bar drags the whole window off with it.

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
        if not under or win32gui.GetAncestor(under, win32con.GA_ROOT) not in game:
            return None
        x, y = win32gui.ScreenToClient(window.hwnd, at)
        _, _, right, bottom = win32gui.GetClientRect(window.hwnd)
        return at if 0 <= x < right and 0 <= y < bottom else None
    except pywintypes.error:
        return None


def held_by_player(interaction):
    """Say whether a mouse button is held on the game window, as when the player grabs its title bar to drag it.

    Args:
        interaction: The running `PostMessageInteraction`, whose `hwnd_window` holds the game's window handles.

    Returns:
        True while the window is dragged or holds the mouse capture. False when it cannot be read.
    """
    window = interaction.hwnd_window
    user32 = ctypes.windll.user32
    thread = user32.GetWindowThreadProcessId(window.top_hwnd or window.hwnd, None)
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    return bool(thread and user32.GetGUIThreadInfo(thread, ctypes.byref(info)) and (info.flags & GUI_INMOVESIZE or info.hwndCapture))


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
    global _frozen
    _frozen = frozen
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


def waiting_out_holds(original):
    """Wrap `PostMessageInteraction.post`, the one call every posted click, key and scroll goes through, to wait while the window is held.

    Frozen input skips the wait, since the player could not let go then. A title bar grab never freezes, as the cursor is outside the client area.

    Args:
        original: Upstream's `post`.

    Returns:
        The wrapped method.
    """
    def post(self, message, *args, **kwargs):
        if message not in RELEASES and not _frozen and held_by_player(self):
            logger.info("the game window is being held, so input waits until it is let go")
            give_up = time.monotonic() + WAIT_LIMIT
            while held_by_player(self):
                if time.monotonic() > give_up:
                    logger.warning(f"the game window was still held after {WAIT_LIMIT}s, so input goes anyway")
                    break
                time.sleep(WAIT_STEP)
        return original(self, message, *args, **kwargs)

    return post


def apply():
    """Keep the real cursor from overriding the bot's clicks and keys, and hold input while the game window is dragged."""
    global _patched
    if _patched:
        return
    from ok.device.interaction import PostMessageInteraction

    PostMessageInteraction.click = borrowing_cursor(PostMessageInteraction.click)
    PostMessageInteraction.send_key = parking_cursor(PostMessageInteraction.send_key)
    PostMessageInteraction.post = waiting_out_holds(PostMessageInteraction.post)
    _patched = True
    logger.info("clicks and keys move the real cursor out of the way while it is over the game")
