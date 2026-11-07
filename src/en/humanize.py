"""Make the bot's clicks, keys and pacing less mechanical, as tuned under the Input Variance settings.

Upstream clicks the exact centre of every box (its "variance" is under a pixel and rounds away), holds every press for 10-20ms and acts the
moment a screen appears. This spreads clicks, varies press lengths and waits a short reaction delay.
"""

import random
import time

from ok import ConfigOption, Logger, og

logger = Logger.get_logger(__name__)

# The labels on the Settings page, and the keys they are saved under.
SPREAD = "Spread Clicks"
SPREAD_PX = "Fixed-Point Spread (px)"
VARY_PRESS = "Vary Press Length"
REACT = "Reaction Delay"
REACT_MIN = "Reaction Delay Min (ms)"
REACT_MAX = "Reaction Delay Max (ms)"

DEFAULTS = {
    SPREAD: True,
    SPREAD_PX: 8,
    VARY_PRESS: True,
    REACT: True,
    REACT_MIN: 150,
    REACT_MAX: 400,
}

# Listed in `global_configs`, which is what puts it on the Settings page. A number row only shows while its switch is on.
human_input_option = ConfigOption("Input Variance", DEFAULTS, config_type={
    SPREAD: {"sub_configs": {True: [SPREAD_PX]}},
    SPREAD_PX: {"min": 0, "max": 12},
    REACT: {"sub_configs": {True: [REACT_MIN, REACT_MAX]}},
    REACT_MIN: {"min": 0, "max": 2000},
    REACT_MAX: {"min": 0, "max": 2000},
}, config_description={
    SPREAD: "Click a random spot near the middle of each button instead of its exact centre.",
    SPREAD_PX: "How far a click aimed at a fixed spot, not a read button, may drift. Measured at 1080p and scaled to the window.",
    VARY_PRESS: "Hold each click and key for a varied 50-140ms instead of a fixed 10-20ms.",
    REACT: "Wait a moment before acting on a new screen, as a person reading it would.",
    REACT_MIN: "Shortest reaction delay.",
    REACT_MAX: "Longest reaction delay.",
}, description="Make clicks, keys and pacing less mechanical.")

# Spread of a box click, as a share of the box: a standard deviation of 15%, kept inside the box's middle 70%.
BOX_SIGMA = 0.15
BOX_INNER = (0.15, 0.85)
# Press lengths in seconds as (shortest, longest, most likely), for a triangular draw. Upstream's click also waits this long before the press.
CLICK_PRESS = (0.06, 0.14, 0.08)
KEY_PRESS = (0.05, 0.12, 0.07)
# A press asked to last longer than this is a deliberate hold and keeps its length.
LONG_HOLD = 0.05
# An input this soon after the last one continues the same burst and skips the reaction delay.
FRESH_LOOK = 0.5
# The frame height `SPREAD_PX` is measured at.
REFERENCE_HEIGHT = 1080

_patched = False
# When the last click or key finished, on the monotonic clock.
_last_input = float("-inf")
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


def pace(tuned):
    """Wait a reaction delay when this input starts a new decision.

    Args:
        tuned: The Input Variance settings.

    Returns:
        The reaction delay waited in seconds, 0 when none was.
    """
    if not tuned[REACT] or time.monotonic() - _last_input < FRESH_LOOK:
        return 0
    wait = random.uniform(tuned[REACT_MIN], tuned[REACT_MAX]) / 1000
    time.sleep(wait)
    return wait


def finished():
    """Note that an input just finished, for the reaction delay."""
    global _last_input
    _last_input = time.monotonic()


def humanizing_click(original):
    """Wrap `PostMessageInteraction.click` with the pacing, the spread and a varied press.

    Args:
        original: The click below, already wrapped by `src/en/cursor.py`.

    Returns:
        The wrapped method.
    """
    def click(self, x=-1, y=-1, *args, down_time=0.01, **kwargs):
        global _aimed
        tuned = settings()
        if not tuned:
            return original(self, x, y, *args, down_time=down_time, **kwargs)
        aimed, _aimed = _aimed, False
        waited = pace(tuned)
        asked = (x, y)
        # -1 repeats the last position, which upstream tracks itself.
        if tuned[SPREAD] and not aimed and x >= 0 and y >= 0:
            x, y = nudge(self, x, y, tuned)
        if tuned[VARY_PRESS] and down_time <= LONG_HOLD:
            down_time = random.triangular(*CLICK_PRESS)
        logger.debug(f"click {asked} lands at ({x}, {y}), held {down_time * 1000:.0f}ms after a {waited * 1000:.0f}ms reaction")
        try:
            return original(self, x, y, *args, down_time=down_time, **kwargs)
        finally:
            finished()

    return click


def humanizing_key(original):
    """Wrap `PostMessageInteraction.send_key` with the pacing and a varied press.

    Args:
        original: The key below, already wrapped by `src/en/cursor.py`.

    Returns:
        The wrapped method.
    """
    def send_key(self, key, down_time=0.01, *args, **kwargs):
        tuned = settings()
        if not tuned:
            return original(self, key, down_time, *args, **kwargs)
        waited = pace(tuned)
        if tuned[VARY_PRESS] and down_time <= LONG_HOLD:
            down_time = random.triangular(*KEY_PRESS)
        logger.debug(f"key {key} held {down_time * 1000:.0f}ms after a {waited * 1000:.0f}ms reaction")
        try:
            return original(self, key, down_time, *args, **kwargs)
        finally:
            finished()

    return send_key


def apply():
    """Spread clicks, vary presses and pace inputs while the Input Variance settings ask for it."""
    global _patched
    if _patched:
        return
    from ok.device.interaction import PostMessageInteraction
    from ok.feature.Box import Box

    Box.relative_with_variance = spreading_in_box(Box.relative_with_variance)
    PostMessageInteraction.click = humanizing_click(PostMessageInteraction.click)
    PostMessageInteraction.send_key = humanizing_key(PostMessageInteraction.send_key)
    _patched = True
    logger.info("clicks and keys follow the Input Variance settings")
