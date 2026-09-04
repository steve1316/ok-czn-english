"""Capture the game window to a PNG, so screens can be read without running the bot.

The Global client renders into a `GLFW30` OpenGL window, which BitBlt and `PrintWindow` cannot read - both
return a black frame. So this brings the window to the front and grabs the desktop region it occupies. That
means the window has to be unobscured for the moment of capture, which is fine for building the OCR catalog
by hand. The bot itself uses the framework's WGC path instead and does not need this.

Captures go to `captures/`, never `screenshots/`: the framework owns the latter and wipes it wholesale once it
passes 300 MB, or on every cleanup in debug mode.

Run `python scripts/capture_window.py <name>` to write `captures/<name>.png`, or add `--watch` to keep
grabbing while you play. Watch mode never steals focus - it only captures while the game is already frontmost,
and it skips frames that look like the one before, so a run leaves one image per distinct screen.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import win32con
import win32gui
from PIL import ImageGrab

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "captures"
WINDOW_TITLE = "Chaos Zero Nightmare"
SETTLE_SECONDS = 0.6
# Two frames counting as the same screen. Measured on idle menus, where an animated background still moves a few
# percent of pixels between grabs, so the threshold sits well above that but below a real screen change.
SAME_SCREEN_RATIO = 0.02
THUMBNAIL = (160, 90)


def find_window(title):
    """Locate the game window by its exact title.

    Args:
        title: The window title to match.

    Returns:
        The window handle.

    Raises:
        SystemExit: When no window with that title is open.
    """
    hwnd = win32gui.FindWindow(None, title)
    if not hwnd:
        raise SystemExit(f"no window titled '{title}' is open, is the game running?")
    return hwnd


def bring_to_front(hwnd):
    """Raise the window and wait for it to finish drawing.

    `SetForegroundWindow` is refused when the calling process does not own the foreground, so the failure is
    tolerated and reported by the caller comparing handles rather than raised here.

    Args:
        hwnd: The window handle to raise.
    """
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(SETTLE_SECONDS)


def capture(hwnd):
    """Grab the screen region covered by one window's client area.

    Args:
        hwnd: The window handle to capture.

    Returns:
        A `PIL.Image` of the window's client area.
    """
    _, _, width, height = win32gui.GetClientRect(hwnd)
    origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
    box = (origin_x, origin_y, origin_x + width, origin_y + height)
    return ImageGrab.grab(bbox=box, all_screens=True)


def fingerprint(image):
    """Reduce an image to a small greyscale array for comparing one frame against the next.

    Args:
        image: A `PIL.Image` to reduce.

    Returns:
        A float array of the downscaled greyscale image.
    """
    return np.asarray(image.convert("L").resize(THUMBNAIL), dtype=float)


def looks_the_same(previous, current, ratio=SAME_SCREEN_RATIO):
    """Report whether two frames show the same screen.

    Args:
        previous: Fingerprint of the earlier frame, or None.
        current: Fingerprint of the frame just grabbed.

    Returns:
        True when the two are close enough to be the same screen.
    """
    if previous is None:
        return False
    return float(np.mean(np.abs(previous - current) > 24)) < ratio


def watch(hwnd, name, interval, ratio):
    """Grab distinct screens for as long as the game stays in front.

    Args:
        hwnd: The window handle to capture.
        name: Basename prefix for the written PNGs.
        interval: Seconds to wait between grabs.

    Returns:
        The number of images written.
    """
    OUT_DIR.mkdir(exist_ok=True)
    previous = None
    written = 0
    print("watching, play normally - press Ctrl-C to stop")
    try:
        while True:
            if win32gui.GetForegroundWindow() == hwnd:
                image = capture(hwnd)
                current = fingerprint(image)
                if not looks_the_same(previous, current, ratio):
                    out_path = OUT_DIR / f"{name}_{written:03d}.png"
                    image.save(out_path)
                    written += 1
                    print(f"{out_path}")
                previous = current
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    return written


def main():
    """Entry point. Writes one capture of the game window, or many in watch mode.

    Returns:
        0 on success, 1 when the window could not be raised and the grab would show whatever is on top.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="basename for the PNG written into captures/")
    parser.add_argument("--title", default=WINDOW_TITLE, help="window title to capture")
    parser.add_argument("--watch", action="store_true", help="keep capturing distinct screens while you play")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between grabs in watch mode")
    parser.add_argument("--threshold", type=float, default=0.06,
                        help="fraction of pixels that must change to count as a new screen")
    args = parser.parse_args()

    hwnd = find_window(args.title)
    if args.watch:
        print(f"wrote {watch(hwnd, args.name, args.interval, args.threshold)} images")
        return 0

    bring_to_front(hwnd)
    if win32gui.GetForegroundWindow() != hwnd:
        print(f"could not raise '{args.title}', click it once and run this again", file=sys.stderr)
        return 1

    image = capture(hwnd)
    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{args.name}.png"
    image.save(out_path)
    print(f"{out_path}  {image.width}x{image.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
