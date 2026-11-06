"""Open the app's own window where it can be reached.

Upstream restores the saved position without checking that a screen is still there, so a window left on an unplugged
monitor opens off-screen with no way to drag it back. Its centred default also puts the title bar above the top of a
screen shorter than the default window, which is common on a laptop with display scaling.
"""

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication

from src.en.framework import import_ui

# Half the framework's 48px title bar, so the point checked sits in the middle of the bar.
TITLE_BAR_MIDDLE = 24

_patched = False


def can_grab(geometry, screens):
    """Check that the middle of a window's title bar is on a screen, which leaves half the bar to drag it by.

    Args:
        geometry: The window's `QRect`, as `geometry()` reports it.
        screens: The available `QRect` of each connected screen, which leaves out the taskbar.

    Returns:
        True when the window can be dragged.
    """
    middle = QPoint(geometry.center().x(), geometry.y() + TITLE_BAR_MIDDLE)
    return any(screen.contains(middle) for screen in screens)


def fitted(width, height, screen):
    """Centre a window on a screen, shrinking it first if it is bigger than the screen.

    Args:
        width: The window's width, from the app's `window_size` config.
        height: The window's height, from the same config.
        screen: The available `QRect` of the screen to centre on.

    Returns:
        The window's `QRect`.
    """
    geometry = QRect(QPoint(0, 0), QSize(width, height).boundedTo(screen.size()))
    geometry.moveCenter(screen.center())
    return geometry


def reachable(original):
    """Wrap `MainWindow.set_window_size` so the window never opens where it cannot be dragged.

    Args:
        original: Upstream's `set_window_size`.

    Returns:
        The replacement method.
    """

    def set_window_size(self, width, height, min_width, min_height):
        original(self, width, height, min_width, min_height)
        # Maximizing ignores the saved position, and giving a maximized window a geometry would un-maximize it.
        if self.isMaximized():
            return
        screens = [screen.availableGeometry() for screen in QGuiApplication.screens()]
        if not can_grab(self.geometry(), screens):
            self.setGeometry(fitted(width, height, QGuiApplication.primaryScreen().availableGeometry()))

    return set_window_size


def apply():
    """Keep the main window reachable when the framework first places it."""
    global _patched
    if _patched:
        return
    main_window = import_ui("MainWindow", "MainWindow")
    if main_window is None:
        return
    main_window.set_window_size = reachable(main_window.set_window_size)
    _patched = True
