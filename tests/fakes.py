"""Stand-ins the tests share, so a fixture means the same thing wherever it is copied.

Eight files grew their own `FakeBox`, and they did not agree. Most placed a box by its share of the screen,
the way a handler's region constants are written, but one placed it in raw pixels under the same class name.
A fixture moved between those two files landed somewhere else entirely and the test still passed.

`units` is keyword-only and has no silent default at the call site for that reason: a box is either a
fraction of the screen or a pixel position, and the file has to say which.
"""

import atexit

import shiboken6
from PySide6.QtWidgets import QApplication

WIDTH, HEIGHT = 1920, 1080


def delete_open_widgets():
    """Delete the widgets tests left open, since a kit widget alive at interpreter exit kills the process after the tests pass."""
    for widget in QApplication.topLevelWidgets():
        # Deleting a window takes its children with it, and a child can be in this list too.
        if shiboken6.isValid(widget):
            shiboken6.delete(widget)


# Handlers run last-registered-first and PySide registers its teardown on import, so the import above puts this ahead of it.
atexit.register(delete_open_widgets)


class FakeBox:
    """An OCR box, positioned by its centre and sized in pixels."""

    def __init__(self, name, center_x, center_y, *, width=90, height=30, units="fraction"):
        """Place a box the way `find_box_at_point` and the region helpers expect to read one.

        Args:
            name: The text OCR read off it.
            center_x: The box centre across the screen, as a fraction unless `units` is "pixels".
            center_y: The box centre down the screen, in the same units as `center_x`.
            width: The box width in pixels.
            height: The box height in pixels.
            units: "fraction" when the centre is a share of the screen, "pixels" when it already is one.

        Raises:
            ValueError: If `units` is neither "fraction" nor "pixels".
        """
        if units not in ("fraction", "pixels"):
            raise ValueError(f"units must be 'fraction' or 'pixels', not {units!r}")
        self.name = name
        self.width, self.height = width, height
        scale_x, scale_y = (WIDTH, HEIGHT) if units == "fraction" else (1, 1)
        self.x = center_x * scale_x - self.width / 2
        self.y = center_y * scale_y - self.height / 2

    def area(self):
        """Return the box area in pixels, which `find_box_at_point` ranks overlapping hits by.

        Returns:
            Width times height.
        """
        return self.width * self.height


class EchoApp:
    """Stands in for the running app's translator, which leaves English game names alone."""

    def tr(self, key):
        """Return the key untouched.

        Args:
            key: The string being translated.

        Returns:
            The same string.
        """
        return key
