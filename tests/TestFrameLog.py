"""Check that a debug run saves one frame per log line a second, named so the line finds it, and keeps only the newest sessions."""

import logging
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.en import frame_log  # noqa: E402

# 00:48:52,268 local time on the day of a live run, as the log line would print it.
LOGGED_AT = time.mktime((2026, 10, 25, 0, 48, 52, 0, 0, -1)) + 0.268


def record(level, at, message="StoryMode:nothing left worth playing"):
    """Build a log record stamped at a fixed time.

    Args:
        level: The record's logging level.
        at: The epoch time the record says it was logged at.
        message: The logged text.

    Returns:
        A `logging.LogRecord`.
    """
    line = logging.LogRecord("ok", level, __file__, 0, message, None, None)
    line.created, line.msecs = at, round((at % 1) * 1000)
    return line


class TestFrameLog(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        # A fresh frame per read, the way the executor hands over each capture.
        self.executor = types.SimpleNamespace(current_task=object(), nullable_frame=lambda: np.full((8, 8, 3), 200, np.uint8))
        self.handler = frame_log.FrameLog(lambda: self.executor, os.path.join(self.folder.name, "session"))
        self.log = logging.Logger("tests.frame_log", logging.DEBUG)
        self.log.addHandler(self.handler)

    def test_a_line_saves_the_frame_it_was_logged_on(self):
        self.log.handle(record(logging.INFO, LOGGED_AT))
        path, frame = self.handler.pending.get_nowait()
        self.assertEqual("00-48-52-268_StoryMode-nothing-left-worth-playing.jpg", os.path.basename(path))
        self.handler.save(path, frame)
        self.assertEqual((8, 8, 3), cv2.imread(path).shape)

    def test_only_one_info_line_a_second_saves_while_a_task_runs(self):
        # Every one of these is a frame saved for nothing, and a battle logs on every frame.
        self.log.handle(record(logging.INFO, LOGGED_AT))
        self.log.handle(record(logging.INFO, LOGGED_AT + 0.2))
        self.log.handle(record(logging.DEBUG, LOGGED_AT + 2))
        self.executor.current_task = None
        self.log.handle(record(logging.INFO, LOGGED_AT + 4))
        self.assertEqual(1, self.handler.pending.qsize())

    def test_only_the_newest_sessions_are_kept(self):
        for name in ("2026-10-22_10-00-00", "2026-10-23_10-00-00", "2026-10-24_10-00-00", "2026-10-25_10-00-00"):
            os.makedirs(os.path.join(self.folder.name, name))
        frame_log.prune(self.folder.name, frame_log.SESSIONS_KEPT - 1)
        self.assertEqual(["2026-10-24_10-00-00", "2026-10-25_10-00-00"], sorted(os.listdir(self.folder.name)))


if __name__ == "__main__":
    unittest.main()
