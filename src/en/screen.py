"""Read positions off the screen the way the handlers talk about them.

Handlers here describe a place as a `(left, top, right, bottom)` box in screen fractions, which is the same
shape upstream uses for `task.box_of_screen` and for its own region literals. The reader hands back pixels,
so something has to convert, and doing it inline is how the same four lines of arithmetic ended up copied
across several modules.

`text_in_region` is the loop those modules actually want. Almost every fork-local handler starts by asking
"is this caption in that band", and writing the walk out per module is how near-identical copies of it keep
appearing next to the copies of the arithmetic.

The screen literals two or more modules share live here too, for the same reason. `find_box_at_point` has no
tolerance at all, so a point that upstream nudges and the fork updates in only one of its copies does not
fail - it silently reads nothing, forever.
"""

# Where the Combatants tab writes each team member's name. Upstream's own numbers, from the read inside
# `handle_archive_target_member`. Both `src/en/navigation.py` and `src/en/rewards.py` work from them.
COMBATANT_NAME_POINTS = ((0.159, 0.368), (0.432, 0.368), (0.705, 0.369))


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


def text_in_region(task, needle, region):
    """Find the first OCR box in a region whose text contains a caption.

    Case is ignored, which costs nothing on the Chinese literals the catalog produces and saves the callers
    that read English straight off the screen from spelling the fold out themselves.

    Args:
        task: The running task, whose `all_texts` holds the current OCR pass.
        needle: The caption to look for, matched as a substring.
        region: A `(left, top, right, bottom)` tuple in screen fractions.

    Returns:
        The matching box, or None when the caption is not in that part of the screen.
    """
    wanted = needle.casefold()
    for box in getattr(task, "all_texts", None) or []:
        if wanted in box.name.casefold() and in_region(box, region, task.width, task.height):
            return box
    return None
