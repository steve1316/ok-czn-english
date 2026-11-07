"""Make the bot's clicks less mechanical, as tuned under the Input Variance settings.

Upstream clicks the exact centre of every box, since its "variance" is under a pixel and rounds away. This spreads clicks around that centre.
"""

import random

from ok import ConfigOption, Logger, og

logger = Logger.get_logger(__name__)

# The labels on the Settings page, and the keys they are saved under.
SPREAD = "Spread Clicks"
SPREAD_PX = "Fixed-Point Spread (px)"

DEFAULTS = {
    SPREAD: True,
    SPREAD_PX: 8,
}

# Listed in `global_configs`, which is what puts it on the Settings page. A number row only shows while its switch is on.
human_input_option = ConfigOption("Input Variance", DEFAULTS, config_type={
    SPREAD: {"sub_configs": {True: [SPREAD_PX]}},
    SPREAD_PX: {"min": 0, "max": 12},
}, config_description={
    SPREAD: "Click a random spot near the middle of each button instead of its exact centre.",
    SPREAD_PX: "How far a click aimed at a fixed spot, not a read button, may drift. Measured at 1080p and scaled to the window.",
}, description="Make clicks, keys and pacing less mechanical.")

# Spread of a box click, as a share of the box: a standard deviation of 15%, kept inside the box's middle 70%.
BOX_SIGMA = 0.15
BOX_INNER = (0.15, 0.85)
# The frame height `SPREAD_PX` is measured at.
REFERENCE_HEIGHT = 1080

_patched = False
# Set by a box click's aim so the click it feeds is not spread a second time.
_aimed = False


def settings():
    """Read the Input Variance settings.

    Returns:
        The settings, or None outside a live run, where nothing is changed.
    """
    return None if og.executor is None else og.global_config.get_config(human_input_option)


def spot(relative):
    """Draw a spread position along one side of a box around the one asked for.

    Args:
        relative: The position asked for, as a share of the box side. A spot outside the middle 70% is kept reachable.

    Returns:
        The drawn share.
    """
    low, high = min(relative, BOX_INNER[0]), max(relative, BOX_INNER[1])
    return min(high, max(low, random.gauss(relative, BOX_SIGMA)))


def spreading_in_box(original):
    """Wrap `Box.relative_with_variance`, the point `click_box` aims at, so it spreads across the box.

    Args:
        original: Upstream's `relative_with_variance`.

    Returns:
        The wrapped method.
    """
    def relative_with_variance(self, relative_x=0.5, relative_y=0.5):
        tuned = settings()
        if not tuned or not tuned[SPREAD]:
            return original(self, relative_x, relative_y)
        global _aimed
        _aimed = True
        return int(round(self.x + self.width * spot(relative_x))), int(round(self.y + self.height * spot(relative_y)))

    return relative_with_variance


def nudge(interaction, x, y, tuned):
    """Drift a fixed click point by a few pixels, staying inside the frame.

    Args:
        interaction: The running `PostMessageInteraction`, whose capture gives the frame size.
        x: The frame x in pixels.
        y: The frame y in pixels.
        tuned: The Input Variance settings.

    Returns:
        The drifted point.
    """
    width, height = interaction.capture.width, interaction.capture.height
    reach = tuned[SPREAD_PX] * height / REFERENCE_HEIGHT
    if reach <= 0:
        return x, y
    dx, dy = (min(reach, max(-reach, random.gauss(0, reach / 2))) for _ in range(2))
    return min(width - 1, max(0, int(round(x + dx)))), min(height - 1, max(0, int(round(y + dy))))


def humanizing_click(original):
    """Wrap `PostMessageInteraction.click` with the spread.

    Args:
        original: The click below, already wrapped by `src/en/cursor.py`.

    Returns:
        The wrapped method.
    """
    def click(self, x=-1, y=-1, *args, **kwargs):
        global _aimed
        tuned = settings()
        if not tuned:
            return original(self, x, y, *args, **kwargs)
        aimed, _aimed = _aimed, False
        asked = (x, y)
        # -1 repeats the last position, which upstream tracks itself.
        if tuned[SPREAD] and not aimed and x >= 0 and y >= 0:
            x, y = nudge(self, x, y, tuned)
        logger.debug(f"click {asked} lands at ({x}, {y})")
        return original(self, x, y, *args, **kwargs)

    return click


def apply():
    """Spread clicks while the Input Variance settings ask for it."""
    global _patched
    if _patched:
        return
    from ok.device.interaction import PostMessageInteraction
    from ok.feature.Box import Box

    Box.relative_with_variance = spreading_in_box(Box.relative_with_variance)
    PostMessageInteraction.click = humanizing_click(PostMessageInteraction.click)
    _patched = True
    logger.info("clicks follow the Input Variance settings")
