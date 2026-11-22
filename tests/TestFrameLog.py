"""Check the debug-run tools: one saved frame per log line a second, and the remote control's seat in the real mode lists."""

import http.client
import http.server
import importlib.util
import json
import logging
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
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

# `scripts/` is no package, so the MCP bridge is loaded from its file.
_spec = importlib.util.spec_from_file_location("czn_mcp", REPO_ROOT / "scripts" / "czn_mcp.py")
czn_mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(czn_mcp)

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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.server_close)
    test.addCleanup(server.shutdown)
    return server.server_port


def raw_post(port, headers, host=True, command="status", body=b"{}", length=None, late=False):
    """POST `body` to a command with exactly `headers`, as a browser or another local program might.

    Args:
        port: The remote control's port.
        headers: Every header to send besides Content-Length, and Host unless `headers` names one.
        host: False to send no Host header at all.
        command: The command the path names.
        body: The bytes sent after the headers.
        length: The Content-Length to send instead of the body's own size.
        late: True to send the body only after the port has read the headers, and to read the reply a moment after
            that, as a slow caller's packets can trail.

    Returns:
        The reply's status, Content-Type and body text.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.putrequest("POST", f"/{command}", skip_host=not host or "Host" in headers)
        for name, value in {**headers, "Content-Length": str(len(body) if length is None else length)}.items():
            connection.putheader(name, value)
        if late:
            connection.endheaders()
            time.sleep(0.05)
            connection.send(body)
            time.sleep(0.3)
        else:
            connection.endheaders(body)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read().decode("utf-8")
    finally:
        connection.close()


def trickle_post(port, headers, length, every):
    """POST to `status` and send the body one byte at a time until the port answers, as a slow or hostile caller might.

    Args:
        port: The remote control's port.
        headers: Every header to send besides Host and Content-Length.
        length: The Content-Length to send.
        every: Seconds between two body bytes.

    Returns:
        The reply's status line, empty when the connection was reset first, and the seconds until the port answered.
    """
    connection = socket.create_connection(("127.0.0.1", port), timeout=15)
    answered = threading.Event()

    def trickle():
        try:
            for _ in range(length):
                if answered.wait(every):
                    return
                connection.sendall(b" ")
        except OSError:
            pass

    head = {"Host": f"127.0.0.1:{port}", **headers, "Content-Length": str(length)}
    sender = threading.Thread(target=trickle, daemon=True)
    started = time.monotonic()
    try:
        lines = "".join(f"{name}: {value}\r\n" for name, value in head.items())
        connection.sendall(f"POST /status HTTP/1.1\r\n{lines}\r\n".encode("ascii"))
        sender.start()
        try:
            first = connection.recv(256)
        except ConnectionError:
            first = b""
        seconds = time.monotonic() - started
        answered.set()
        sender.join()
        return first.split(b"\r\n")[0].decode("ascii"), seconds
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

    def test_the_mcp_bridge_reaches_the_port(self):
        """The port's own guards must never shut out the one caller it is there for."""
        port = serve_remote(self)
        ran = []
        with standing_in(remote, status=lambda **kwargs: ran.append(kwargs) or "status ran", _last_contact=None), \
                standing_in(czn_mcp, URL=f"http://127.0.0.1:{port}"):
            self.assertEqual("status ran", czn_mcp.call("status"))
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

    def test_a_reply_reaches_a_caller_whose_body_trails_the_headers(self):
        """Body bytes that land after the port closes make Windows reset the connection and wipe the unread reply."""
        port = serve_remote(self)
        refused = {
            "text/plain": ({"Content-Type": "text/plain"}, 415),
            "an Origin": ({"Content-Type": "application/json", "Origin": "https://example.com"}, 403),
            "a foreign Host": ({"Content-Type": "application/json", "Host": f"rebound.example:{port}"}, 403),
        }
        ran = []
        with standing_in(remote, status=lambda **kwargs: ran.append(kwargs) or "status ran", _last_contact=None):
            for case, (headers, status) in refused.items():
                with self.subTest(case):
                    code, _, text = raw_post(port, headers, late=True)
                    self.assertEqual(status, code)
                    self.assertTrue(text.startswith("refused: "), text)
                    self.assertIsNone(remote._last_contact)
            with self.subTest("an unknown command"):
                code, _, text = raw_post(port, {"Content-Type": "application/json"}, command="exit", late=True)
                self.assertEqual(200, code)
                self.assertIn("unknown command", json.loads(text)["error"])
        self.assertEqual([], ran)

    def test_a_refused_body_that_never_comes_holds_the_refusal_back_only_briefly(self):
        """A page could send a Content-Length it never fills, and the port must not wait on it for good."""
        port = serve_remote(self)
        with standing_in(remote, DRAIN_TIMEOUT=1):
            for case, length, body, seconds in (("never filled", 10 ** 9, b"{}", 3), ("negative", -1, b"", 0.5),
                                                ("not a number", "two", b"", 0.5)):
                with self.subTest(case):
                    started = time.monotonic()
                    code, _, text = raw_post(port, {"Content-Type": "text/plain"}, body=body, length=length)
                    self.assertEqual(415, code)
                    self.assertTrue(text.startswith("refused: "), text)
                    self.assertLess(time.monotonic() - started, seconds)

    def test_a_trickled_body_holds_the_handler_for_one_deadline_in_all(self):
        """A byte at a time keeps each read inside its timeout, so only a deadline for the whole body ends it."""
        port = serve_remote(self)
        ran = []
        cases = (("refused", {"Content-Type": "text/plain"}, 415),
                 ("served", {"Content-Type": "application/json"}, 408))
        with standing_in(remote, DRAIN_TIMEOUT=1, status=lambda **kwargs: ran.append(kwargs) or "status ran",
                         _last_contact=None):
            for case, headers, status in cases:
                with self.subTest(case):
                    line, seconds = trickle_post(port, headers, length=20, every=0.3)
                    self.assertRegex(line, rf"^HTTP/1\.\d {status} ")
                    self.assertLess(seconds, 2)
                    self.assertIsNone(remote._last_contact)
        self.assertEqual([], ran)

    def test_a_served_content_length_the_port_cannot_trust_is_refused_at_once(self):
        """Taken as given, -1 waits until the caller closes, and a word or 5000 digits raise a ValueError."""
        port = serve_remote(self)
        own = {"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"}
        ran = []
        cases = (("negative", -1, b"", 400, 0.5), ("not a number", "two", b"", 400, 0.5),
                 ("over the limit", remote.DRAIN_LIMIT + 1, b"{}", 413, 2), ("5000 digits", "9" * 5000, b"{}", 413, 2),
                 ("never filled", 10, b"{}", 408, 2))
        with standing_in(remote, DRAIN_TIMEOUT=1, status=lambda **kwargs: ran.append(kwargs) or "status ran",
                         _last_contact=None):
            for case, length, body, status, seconds in cases:
                with self.subTest(case):
                    started = time.monotonic()
                    code, content_type, text = raw_post(port, own, body=body, length=length)
                    self.assertEqual((status, "text/plain; charset=utf-8"), (code, content_type))
                    self.assertTrue(text.startswith("refused: "), text)
                    self.assertLess(time.monotonic() - started, seconds)
                    self.assertIsNone(remote._last_contact)
            self.assertEqual([], ran)
            # HTTP allows leading zeros, and the count they pad is small, so it is served like the count alone.
            with self.subTest("a small count padded with 5000 zeros"):
                code, _, text = raw_post(port, own, body=b"{}", length="0" * 5000 + "2")
                self.assertEqual((200, {"ok": True, "result": "status ran"}), (code, json.loads(text)))
                self.assertEqual([{}], ran)

    def test_a_chunked_body_is_refused_and_runs_nothing(self):
        """Read as an empty body, a chunked `hold` sending `{"on": false}` would hold the bot, not release it."""
        port = serve_remote(self)
        ran = []
        for case, extra in (("no Content-Length", {}), ("a Content-Length beside it", {"Content-Length": "13"})):
            with self.subTest(case), standing_in(remote, hold=lambda **kwargs: ran.append(kwargs) or "hold ran",
                                                 _last_contact=None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                started = time.monotonic()
                try:
                    headers = {"Content-Type": "application/json", "Transfer-Encoding": "chunked", **extra}
                    # Encoded here, since http.client stops encoding chunks once it sees a Content-Length.
                    body = b'7\r\n{"on": \r\n6\r\nfalse}\r\n0\r\n\r\n'
                    connection.request("POST", "/hold", body=body, headers=headers)
                    response = connection.getresponse()
                    code, content_type = response.status, response.getheader("Content-Type")
                    text = response.read().decode("utf-8")
                finally:
                    connection.close()
                self.assertEqual((411, "text/plain; charset=utf-8"), (code, content_type))
                self.assertTrue(text.startswith("refused: "), text)
                # Read up to the last chunk, not left on the socket to reset the reply or waited on to the deadline.
                self.assertLess(time.monotonic() - started, 1)
                self.assertIsNone(remote._last_contact)
        self.assertEqual([], ran)

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
