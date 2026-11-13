"""Check that the bot's clicks and keys move the real cursor out of the way only while it sits over the game window.

These drive upstream's own `PostMessageInteraction`, with only the Windows calls faked, so a rename upstream fails here.
"""

import ctypes
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import win32con

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ok.device.interaction import PostMessageInteraction  # noqa: E402

from src.en import cursor  # noqa: E402
from tests.fakes import HEIGHT, WIDTH  # noqa: E402

GAME = 10
OTHER = 99
# Where the game's client area sits on screen.
ORIGIN = (100, 200)
# Where the player left the cursor.
PLAYER = (500, 500)
# On the game window's title bar, just above the client area.
TITLE_BAR = (500, ORIGIN[1] - 20)


class Desktop:
    """Fake the Windows calls, recording cursor moves and posted messages in the order they happen."""

    def __init__(self, under=GAME, at=PLAYER, drag=0):
        """Set up a desktop with the cursor over one window.

        Args:
            under: The window under the cursor, `GAME` or `OTHER`.
            at: The cursor's screen position.
            drag: How many checks find the player still holding the game window before they let go.
        """
        self.under = under
        self.at = at
        self.drag = drag
        self.events = []
        # Whether the bot's own press is down, which gives the game window the mouse capture as a real press does.
        self.pressed = False

    def post(self, message):
        """Record a posted message, tracking the press it starts or ends."""
        self.events.append(("post", message))
        self.pressed = {win32con.WM_LBUTTONDOWN: True, win32con.WM_LBUTTONUP: False}.get(message, self.pressed)

    def held_by_player(self, interaction):
        """Report the hold for the first `drag` checks, recording each one, and the capture the bot's own press takes."""
        if self.drag:
            self.drag -= 1
            self.events.append(("dragged",))
            return True
        if self.pressed:
            raise AssertionError("input waited on the capture of the bot's own press, which would never let go")
        return False

    def patches(self):
        """Build the patches that route the Windows calls here.

        Returns:
            The patchers, to start together.
        """
        return [
            mock.patch("win32api.GetCursorPos", return_value=self.at),
            mock.patch("win32gui.GetClientRect", return_value=(0, 0, WIDTH, HEIGHT)),
            mock.patch("win32api.SetCursorPos", side_effect=lambda point: self.events.append(("cursor", tuple(point)))),
            mock.patch("win32gui.WindowFromPoint", side_effect=lambda point: self.under),
            mock.patch("win32gui.GetAncestor", side_effect=lambda hwnd, flag: hwnd),
            mock.patch("win32gui.ClientToScreen", side_effect=lambda hwnd, p: (p[0] + ORIGIN[0], p[1] + ORIGIN[1])),
            mock.patch("win32gui.ScreenToClient", side_effect=lambda hwnd, p: (p[0] - ORIGIN[0], p[1] - ORIGIN[1])),
            mock.patch("win32gui.PostMessage", side_effect=lambda hwnd, message, *args: self.post(message)),
            mock.patch.object(cursor, "held_by_player", side_effect=self.held_by_player),
            mock.patch("time.sleep"),
            mock.patch.object(ctypes.windll.user32, "BlockInput", side_effect=lambda frozen: self.events.append(("freeze", frozen))),
        ]


def interaction():
    """Build upstream's interaction on a game window that is its own top window."""
    window = SimpleNamespace(hwnd=GAME, top_hwnd=0, hwnds=[], get_top_window_cords=lambda x, y: (x, y))
    return PostMessageInteraction(SimpleNamespace(width=WIDTH, height=HEIGHT), window)


class TestCursor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cursor.apply()

    def run_on(self, desktop, action):
        """Run an action on the fake desktop and return what it recorded."""
        patchers = desktop.patches()
        for patcher in patchers:
            patcher.start()
        try:
            action(interaction())
        finally:
            for patcher in patchers:
                patcher.stop()
        return desktop.events

    def test_a_click_over_the_game_presses_on_the_target_and_gives_the_cursor_back(self):
        events = self.run_on(Desktop(), lambda it: it.click(300, 400))
        moves = [event for event in events if event[0] == "cursor"]
        self.assertEqual(moves, [("cursor", (400, 600)), ("cursor", PLAYER)])
        # The press and release both land while the cursor is still on the target.
        on, back = events.index(moves[0]), events.index(moves[1])
        self.assertLess(on, events.index(("post", win32con.WM_LBUTTONDOWN)))
        self.assertLess(events.index(("post", win32con.WM_LBUTTONUP)), back)
        # The player's input is frozen across the whole trip, and always released after it.
        self.assertEqual((events[0], events[-1]), (("freeze", True), ("freeze", False)))

    def test_a_key_over_the_game_parks_the_cursor_clear_of_the_hand(self):
        events = self.run_on(Desktop(), lambda it: it.send_key("1"))
        park = (round(cursor.PARK[0] * WIDTH) + ORIGIN[0], round(cursor.PARK[1] * HEIGHT) + ORIGIN[1])
        self.assertEqual([event for event in events if event[0] == "cursor"], [("cursor", park)])
        self.assertLess(events.index(("cursor", park)), events.index(("post", win32con.WM_KEYDOWN)))

    def test_the_cursor_is_left_alone_while_it_is_off_the_game(self):
        # The title bar case: moving a cursor that holds the title bar drags the game window off-screen.
        for where, desktop in (("other window", lambda: Desktop(under=OTHER)), ("title bar", lambda: Desktop(at=TITLE_BAR))):
            for name, action in (("click", lambda it: it.click(300, 400)), ("key", lambda it: it.send_key("1"))):
                with self.subTest(where=where, action=name):
                    events = self.run_on(desktop(), action)
                    self.assertFalse([event for event in events if event[0] in ("cursor", "freeze")])

    def test_input_waits_while_the_player_drags_the_window(self):
        # Posted mid-drag, a click's position is read as where the drag went, and the window jumps there.
        for name, action in (("click", lambda it: it.click(300, 400)), ("key", lambda it: it.send_key("1"))):
            with self.subTest(name):
                events = self.run_on(Desktop(at=TITLE_BAR, drag=2), action)
                posts = [index for index, event in enumerate(events) if event[0] == "post"]
                self.assertTrue(posts)
                # Both checks that still find the drag come before anything is posted.
                self.assertEqual(events[:min(posts)].count(("dragged",)), 2)

    def test_frozen_input_never_waits_on_a_hold(self):
        # The player cannot let go while input is frozen, so waiting there would hang until Ctrl+Alt+Del.
        desktop = Desktop(drag=1000)
        events = self.run_on(desktop, lambda it: it.click(300, 400))
        self.assertIn(("post", win32con.WM_LBUTTONUP), events)
        self.assertEqual(desktop.drag, 1000)

    def test_a_hold_counts_from_the_press_not_from_when_windows_starts_the_drag(self):
        # A still title bar hold took ~1s live to set the drag flag, but the window held the mouse capture from the press.
        window = SimpleNamespace(hwnd_window=SimpleNamespace(hwnd=GAME, top_hwnd=0))
        for flags, capture, held in ((0, 0, False), (0, GAME, True), (cursor.GUI_INMOVESIZE, GAME, True)):
            def fill(thread, info):
                info._obj.flags, info._obj.hwndCapture = flags, capture
                return 1
            with (self.subTest(flags=flags, capture=capture),
                  mock.patch.object(ctypes.windll.user32, "GetWindowThreadProcessId", return_value=7),
                  mock.patch.object(ctypes.windll.user32, "GetGUIThreadInfo", side_effect=fill)):
                self.assertEqual(cursor.held_by_player(window), held)


if __name__ == "__main__":
    unittest.main()
