"""Stand-ins the tests share, so a fixture means the same thing wherever it is copied.

Eight files grew their own `FakeBox`, and they did not agree. Most placed a box by its share of the screen,
the way a handler's region constants are written, but one placed it in raw pixels under the same class name.
A fixture moved between those two files landed somewhere else entirely and the test still passed.

`units` is keyword-only and has no silent default at the call site for that reason: a box is either a
fraction of the screen or a pixel position, and the file has to say which.
"""

WIDTH, HEIGHT = 1920, 1080


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
