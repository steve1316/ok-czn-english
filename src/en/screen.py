"""Read positions off the screen the way the handlers talk about them.

Handlers here describe a place as a `(left, top, right, bottom)` box in screen fractions, which is the same
shape upstream uses for `task.box_of_screen` and for its own region literals. The reader hands back pixels,
so something has to convert, and doing it inline is how the same four lines of arithmetic ended up copied
across several modules.
"""


def in_region(box, region, width, height):
    """Report whether a box's centre sits inside a relative region.

    The centre rather than the whole box, so a line of text that overruns a band's edge still counts as being
    in it. Upstream's `in_boundary` tests full containment, which drops exactly the wide boxes worth finding.

    Args:
        box: The OCR box.
        region: A `(left, top, right, bottom)` tuple in screen fractions.
        width: Screen width in pixels.
        height: Screen height in pixels.

    Returns:
        True when the box centre is inside the region.
    """
    left, top, right, bottom = region
    center_x = (box.x + box.width / 2) / width
    center_y = (box.y + box.height / 2) / height
    return left <= center_x <= right and top <= center_y <= bottom
