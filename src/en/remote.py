"""Serve a debug run's frame, OCR and settings on localhost, and take clicks between its frames.

`main_debug.py` answers a few JSON commands for `scripts/czn_mcp.py`, so a screen can be read and a button pressed with
nobody at the desk. Clicks queue for a handler at the top of every mode's list, so they land on the bot's own thread
between frames and never race its handlers. Release runs never start it.
"""

import base64
import concurrent.futures
import http.server
import json
import queue
import threading

import cv2

from ok import Logger

from src.en import frame_log
from src.en.handlers import each_list, register
from src.en.screen import centre_of

logger = Logger.get_logger(__name__)

# Loopback only, so nothing off this machine can reach it. `scripts/czn_mcp.py` carries the same address.
HOST = "127.0.0.1"
PORT = 47821
# Seconds an action waits for the bot's page loop. A battle keeps the loop for its whole length.
ACTION_TIMEOUT = 15
# Seconds the bot waits after a remote click or key before reading the next frame.
AFTER_INPUT = 1
# JPEG quality for frames sent out. A 1080p frame comes to ~0.3 MB.
QUALITY = 90
# The task a settings command reads when none is named.
DEFAULT_TASK = "ChaosMode"
# The functions below a request may name, so a path can never reach anything else in the module.
COMMANDS = ("status", "screenshot", "texts", "click", "press_key", "hold", "settings", "set_setting", "set_running")

# Actions waiting for the bot's thread, as `(action, future)` pairs.
_actions = queue.Queue()
# Set while the bot is held, so every frame goes to the remote handler and nothing else acts on it.
_held = threading.Event()
_patched = False


class Remote(http.server.BaseHTTPRequestHandler):
    """Answer `POST /<command>` with a JSON body of keyword arguments, replying `{"ok", "result" | "error"}`."""

    def do_POST(self):
        """Run one command and reply with its result, or with the error it raised."""
        name = self.path.strip("/")
        try:
            if name not in COMMANDS:
                raise KeyError(f"unknown command {name!r}, expected one of {', '.join(COMMANDS)}")
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            reply = {"ok": True, "result": globals()[name](**json.loads(body or b"{}"))}
        except Exception as error:
            reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        data = json.dumps(reply, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        """Keep each request out of the console."""


def handle_remote(task):
    """Run the actions queued for the bot's thread, and take the frame while the bot is held.

    Args:
        task: The running mode task.

    Returns:
        True when an action ran or the bot is held, so no other handler acts on this frame.
    """
    ran = False
    while True:
        try:
            action, future = _actions.get_nowait()
        except queue.Empty:
            return ran or _held.is_set()
        # False once the caller gave up waiting, so a late click never lands on a screen nobody is looking at.
        if not future.set_running_or_notify_cancel():
            continue
        try:
            future.set_result(action(task))
        except Exception as error:
            future.set_exception(error)
        ran = True


def install():
    """Put `handle_remote` first in every mode's list, ahead even of `handle_auto_stop`, so a held bot does nothing at all."""
    for _, handlers in each_list():
        # Matched by name: `claims.py` wraps it, and the install runs once per task load.
        if not any(getattr(handler, "__name__", None) == handle_remote.__name__ for handler in handlers):
            handlers.insert(0, handle_remote)


def on_bot_thread(action):
    """Queue an action for `handle_remote` and wait for it to run.

    Args:
        action: Takes the running mode task. Its return value is passed back.

    Returns:
        What `action` returned.

    Raises:
        TimeoutError: The page loop did not come round in `ACTION_TIMEOUT` seconds. The action is dropped, not left queued.
    """
    future = concurrent.futures.Future()
    _actions.put((action, future))
    try:
        return future.result(ACTION_TIMEOUT)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError(f"the page loop did not come round in {ACTION_TIMEOUT}s - no mode is running, or a battle has the loop")


def _executor():
    """Return ok-script's task executor.

    Raises:
        RuntimeError: The executor has not been built yet.
    """
    from ok import og

    if og.executor is None:
        raise RuntimeError("the task executor has not started")
    return og.executor


def _task(name):
    """Find a task by its class name, such as `ChaosMode`.

    Args:
        name: The class name a request gave.

    Raises:
        KeyError: No task has that name.
    """
    for task in _executor().get_all_tasks():
        if type(task).__name__ == name:
            return task
    raise KeyError(f"no task named {name!r}")


def status():
    """Report which task is running, whether the bot is held, and which tasks are switched on. The modes count as tasks here."""
    executor = _executor()
    current = executor.current_task
    return {
        "running": type(current).__name__ if current is not None else None,
        "held": _held.is_set(),
        "pending": _actions.qsize(),
        "enabled": {type(task).__name__: task.enabled for task in executor.get_all_tasks()},
    }


def screenshot():
    """Return the frame the bot last read, as base64 JPEG.

    Raises:
        RuntimeError: Nothing has been captured yet.
    """
    frame = frame_log.latest()
    if frame is None:
        raise RuntimeError("no frame captured yet")
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
    return {"jpeg": base64.b64encode(jpeg.tobytes()).decode("ascii"), "width": frame.shape[1], "height": frame.shape[0]}


def texts():
    """Return the text the running mode read on its last page-loop frame, with centres as fractions of the frame.

    Raises:
        RuntimeError: The running task keeps no OCR pass, which also covers no task running.
    """
    task = _executor().current_task
    boxes = getattr(task, "all_texts", None)
    if boxes is None:
        raise RuntimeError("the running task keeps no OCR pass")
    centres = [centre_of(box, task.width, task.height) for box in boxes]
    return [{"text": box.name, "x": round(x, 3), "y": round(y, 3)} for box, (x, y) in zip(boxes, centres)]


def _send(label, act):
    """Log one input and run it on the bot's thread.

    Args:
        label: What the log line calls the input.
        act: Takes the running mode task and sends the input.
    """
    def sending(task):
        logger.info(f"remote {label}")
        act(task)

    on_bot_thread(sending)
    return label


def click(x, y):
    """Click a point on the bot's thread, between two frames.

    Args:
        x: Horizontal position as a fraction of the frame, 0 to 1.
        y: Vertical position as a fraction of the frame, 0 to 1.
    """
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("x and y are fractions of the frame, from 0 to 1")
    return _send(f"click at ({x:.3f}, {y:.3f})", lambda task: task.click(x, y, after_sleep=AFTER_INPUT))


def press_key(key):
    """Press a key on the bot's thread, between two frames.

    Args:
        key: The key name ok-script sends, such as `esc`.
    """
    return _send(f"key {key}", lambda task: task.send_key(key, after_sleep=AFTER_INPUT))


def hold(on=True):
    """Stop the bot acting on frames, or let it carry on. A held bot still reads every frame, so `texts` stays current.

    Args:
        on: True to hold the bot, False to release it.
    """
    if on:
        _held.set()
    else:
        _held.clear()
    logger.info(f"remote {'hold' if on else 'release'}")
    return status()


def settings(task=DEFAULT_TASK):
    """Return every setting a task carries, by its config key.

    Args:
        task: The task's class name.
    """
    return dict(_task(task).config)


def set_setting(key, value, task=DEFAULT_TASK):
    """Change one setting on a task, saved to its config file as the settings card would.

    Args:
        key: The config key, which for upstream's settings is the Chinese one.
        value: The new value, of the type the setting already holds.
        task: The task's class name.

    Raises:
        KeyError: The task has no such setting.
        ValueError: ok-script's validation refused the value.
    """
    config = _task(task).config
    if key not in config:
        raise KeyError(f"{task} has no setting {key!r}")
    config[key] = value
    if config[key] != value:
        raise ValueError(f"{task} refused {value!r} for {key!r}")
    logger.info(f"remote set {task} {key} = {value!r}")
    return config[key]


def set_running(task, running):
    """Start or stop a mode, as its Start and Stop buttons would.

    Args:
        task: The mode's class name, such as `ChaosMode`.
        running: True to start it, False to stop it.
    """
    from ok import og

    target = _task(task)
    if running:
        # Posted to the controller's own thread, which finds the game window first as the button does.
        og.app.start_controller.start(target)
    else:
        target.disable()
        target.unpause()
    logger.info(f"remote {'start' if running else 'stop'} {task}")
    return status()


def apply():
    """Serve the remote control, on a debug run only."""
    global _patched
    if _patched:
        return
    _patched = True
    from ok import og

    if not (og.config or {}).get("debug"):
        return
    register(install)
    try:
        server = http.server.ThreadingHTTPServer((HOST, PORT), Remote)
    except OSError as error:
        logger.warning(f"remote control could not listen on {HOST}:{PORT}: {error}")
        return
    threading.Thread(target=server.serve_forever, name="remote", daemon=True).start()
    logger.info(f"debug run, remote control listening on http://{HOST}:{PORT}")
