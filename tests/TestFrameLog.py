"""Check the debug-run tools: one saved frame per log line a second, and the remote control's seat in the real mode lists."""

import http.client
import http.server
import json
import logging
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.request
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ok_tasks"))

import utils_chaos  # noqa: E402
import utils_sortie  # noqa: E402
import utils_story  # noqa: E402

from ok import TaskExecutor  # noqa: E402

from src.en import frame_log, remote  # noqa: E402
from src.en.handlers import standing_in  # noqa: E402

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
        self.executor = types.SimpleNamespace(current_task=object())
        # A fresh frame per read, the way ok-script hands over each capture.
        self.enterContext(standing_in(frame_log, latest=lambda: np.full((8, 8, 3), 200, np.uint8)))
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

    def test_a_full_session_drops_its_oldest_frames(self):
        paths = [os.path.join(self.folder.name, "session", f"{index}.jpg") for index in range(3)]
        frame = np.full((8, 8, 3), 200, np.uint8)
        self.handler.save(paths[0], frame)
        with standing_in(frame_log, SESSION_CAP=os.path.getsize(paths[0]) * 2):
            for path in paths[1:]:
                self.handler.save(path, frame)
        self.assertEqual([False, True, True], [os.path.exists(path) for path in paths])

    def test_only_the_newest_sessions_are_kept(self):
        for name in ("2026-10-22_10-00-00", "2026-10-23_10-00-00", "2026-10-24_10-00-00", "2026-10-25_10-00-00"):
            os.makedirs(os.path.join(self.folder.name, name))
        frame_log.prune(self.folder.name, frame_log.SESSIONS_KEPT - 1)
        self.assertEqual(["2026-10-24_10-00-00", "2026-10-25_10-00-00"], sorted(os.listdir(self.folder.name)))


def serve_remote(test):
    """Serve the remote control on a free loopback port for one test, and return the port."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), remote.Remote)
    # Polled often, since `shutdown` otherwise waits up to half a second for the loop to notice.
    threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server.server_port


def raw_post(port, headers, host=True, command="status", body=b"{}"):
    """POST `body` to a command with exactly `headers`, as a browser or another local program might.

    Args:
        port: The remote control's port.
        headers: Every header to send besides Host unless `headers` names one, and besides the body's Content-Length
            unless `headers` names a Content-Length or a Transfer-Encoding. Naming either sends no body at all.
        host: False to send no Host header at all.
        command: The command the path names.
        body: The bytes to send. Dropped when `headers` names its own length, since the server refuses those unread and
            leftover bytes make Windows reset the connection over the reply.

    Returns:
        The reply's status, Content-Type and body text.
    """
    if "Transfer-Encoding" in headers or "Content-Length" in headers:
        body = None
    else:
        headers = {**headers, "Content-Length": str(len(body))}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest("POST", f"/{command}", skip_host=not host or "Host" in headers)
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders(body)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read().decode("utf-8")
    finally:
        connection.close()


class TestRemote(unittest.TestCase):

    def tearDown(self):
        remote._held.clear()

    def test_the_remote_comes_first_in_every_mode(self):
        """Anywhere lower, a held bot still runs whatever comes before it, and a mode it misses can never be clicked in."""
        remote.install()
        remote.install()
        for module in (utils_chaos, utils_sortie, utils_story):
            with self.subTest(module.__name__):
                names = [handler.__name__ for handler in module.PAGE_HANDLERS]
                self.assertEqual((remote.handle_remote.__name__, 1), (names[0], names.count(names[0])))

    def test_an_abandoned_click_never_lands(self):
        """A click whose caller gave up would otherwise land on whatever screen the bot reaches next."""
        clicks = []
        with standing_in(remote, ACTION_TIMEOUT=0.01), self.assertRaises(TimeoutError):
            remote.on_bot_thread(clicks.append)
        self.assertFalse(remote.handle_remote("task"))
        self.assertEqual([], clicks)

    def test_a_held_bot_gives_up_every_frame(self):
        """Otherwise the bot acts on the screen being stepped through by hand."""
        remote._held.set()
        self.assertTrue(remote.handle_remote("task"))

    def test_a_plain_local_post_reaches_the_port(self):
        """The port's own guards must never shut out a local tool like the MCP bridge, which posts JSON with urllib."""
        port = serve_remote(self)
        ran = []
        request = urllib.request.Request(f"http://127.0.0.1:{port}/status", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        with standing_in(remote, status=lambda **kwargs: ran.append(kwargs) or "status ran", _last_contact=None):
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual({"ok": True, "result": "status ran"}, json.loads(response.read()))
            self.assertIsNotNone(remote._last_contact)
        self.assertEqual([{}], ran)

    def test_a_request_a_web_page_could_send_runs_nothing(self):
        """Loopback alone lets any page open in a browser here click, start a mode or change a setting through the port."""
        port = serve_remote(self)
        own_host = f"127.0.0.1:{port}"
        refused = {
            "text/plain": ({"Content-Type": "text/plain"}, True, 415),
            "no Content-Type": ({}, True, 415),
            "a form": ({"Content-Type": "application/x-www-form-urlencoded"}, True, 415),
            "a multipart form": ({"Content-Type": "multipart/form-data; boundary=x"}, True, 415),
            "JSON in another type's parameter": ({"Content-Type": "text/plain; x=application/json"}, True, 415),
            "an Origin": ({"Content-Type": "application/json", "Origin": "https://example.com"}, True, 403),
            "an Origin of null": ({"Content-Type": "application/json", "Origin": "null"}, True, 403),
            "a foreign Host": ({"Content-Type": "application/json", "Host": f"rebound.example:{port}"}, True, 403),
            "our address as a prefix": ({"Content-Type": "application/json", "Host": f"127.0.0.1.evil.example:{port}"}, True, 403),
            "another port in Host": ({"Content-Type": "application/json", "Host": f"127.0.0.1:{port + 1}"}, True, 403),
            "a Host with no port": ({"Content-Type": "application/json", "Host": "localhost"}, True, 403),
            "no Host": ({"Content-Type": "application/json"}, False, 403),
            # Read as an empty body, a chunked `hold` sending `{"on": false}` would hold the bot, not release it.
            "a chunked body": ({"Content-Type": "application/json", "Transfer-Encoding": "chunked"}, True, 411),
            "chunked beside a Content-Length": (
                {"Content-Type": "application/json", "Transfer-Encoding": "chunked", "Content-Length": "7"}, True, 411),
            # Taken as given, -1 reads until the caller closes, and a word or 5000 digits raise a ValueError.
            "a negative Content-Length": ({"Content-Type": "application/json", "Content-Length": "-1"}, True, 400),
            "a Content-Length that is no number": ({"Content-Type": "application/json", "Content-Length": "two"}, True, 400),
            "a body over the limit": (
                {"Content-Type": "application/json", "Content-Length": str(remote.BODY_LIMIT + 1)}, True, 413),
            "a Content-Length of 5000 digits": ({"Content-Type": "application/json", "Content-Length": "9" * 5000}, True, 413),
        }
        served = {
            "plain JSON": {"Content-Type": "application/json", "Host": own_host},
            "JSON with a charset": {"Content-Type": "application/json; charset=utf-8", "Host": own_host},
            "JSON in capitals": {"Content-Type": "Application/JSON", "Host": own_host},
            "localhost": {"Content-Type": "application/json", "Host": f"LocalHost:{port}"},
        }
        ran = []
        with standing_in(remote, status=lambda **kwargs: ran.append(kwargs) or "status ran", _last_contact=None):
            for case, (headers, host, status) in refused.items():
                with self.subTest(case):
                    ran.clear()
                    remote._last_contact = None
                    code, content_type, text = raw_post(port, headers, host)
                    self.assertEqual((status, "text/plain; charset=utf-8"), (code, content_type))
                    self.assertTrue(text.startswith("refused: "), text)
                    self.assertEqual([], ran)
                    self.assertIsNone(remote._last_contact)
            for case, headers in served.items():
                with self.subTest(case):
                    ran.clear()
                    code, content_type, text = raw_post(port, headers)
                    self.assertEqual((200, {"ok": True, "result": "status ran"}), (code, json.loads(text)))
                    self.assertEqual([{}], ran)

    def test_a_screenshot_outlives_the_frame_ok_script_drops(self):
        """ok-script drops its frame on every sleep, so a held bot would otherwise have nothing to show."""
        self.assertIn("next_frame", vars(TaskExecutor))
        captured = np.zeros((9, 16, 3), np.uint8)
        with standing_in(TaskExecutor, next_frame=lambda executor: captured), standing_in(frame_log, _latest=None):
            frame_log.keep_frames()
            TaskExecutor.next_frame(None)
            self.assertEqual(16, remote.screenshot()["width"])


if __name__ == "__main__":
    unittest.main()
