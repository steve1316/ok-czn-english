"""Stop the bundled adb server on exit, so the Launcher sees the app as closed.

Upstream scans for Android emulators on every start, which spawns the bundled adb.exe as a detached server that
outlives the app. The Launcher counts any process running from the install folder as the app, so every relaunch
asked to Stop App first.
"""

import atexit
import os

from ok import Logger

logger = Logger.get_logger(__name__)

# Process names the adb server runs under.
ADB_NAMES = ("adb.exe", "adb")

_patched = False


def stop_bundled_adb():
    """Kill every adb server started from the copy of adb bundled with this install.

    An adb running from anywhere else belongs to another tool, so it is left alone. This runs while the process
    exits, so it logs a failure rather than raising one.
    """
    try:
        import psutil
        from adbutils._utils import _get_bin_dir

        bin_dir = os.path.normcase(os.path.abspath(_get_bin_dir()))
        for proc in psutil.process_iter(["name", "exe"]):
            exe = proc.info.get("exe")
            if proc.info.get("name") not in ADB_NAMES or not exe or os.path.normcase(os.path.dirname(exe)) != bin_dir:
                continue
            try:
                proc.kill()
                logger.info(f"stopped the bundled adb server, pid {proc.pid}")
            except psutil.Error as e:
                logger.warning(f"could not stop the bundled adb server, pid {proc.pid}: {e}")
    except Exception as e:
        logger.warning(f"could not look for the bundled adb server: {e}")


def apply():
    """Register `stop_bundled_adb` to run when the app exits."""
    global _patched
    if _patched:
        return
    _patched = True
    atexit.register(stop_bundled_adb)
