"""Keep the device list on the PC game window, and keep its Refresh from waiting on emulators that are not running.

Upstream lists emulators above the PC window and, once the saved pick is gone, falls back to a connected emulator. The
saved PC pick names the window handle, which changes every game restart, so a running emulator kept taking over. Its
Refresh also dials every installed emulator and reads every process's command line, so each one waited seconds.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# Installed emulators are reached on the loopback address. A phone on the network is not, and is always dialled.
# Windows refuses a dial to a closed loopback port only after ~2.1s, measured per closed emulator.
LOOPBACK = "127.0.0.1:"
# Where an emulator's adb port listens.
LISTEN_HOSTS = ("127.0.0.1", "0.0.0.0")

_patched = False


def listening_ports():
    """Read which local TCP ports something is listening on (~0.5ms).

    Returns:
        The set of port numbers, or None when the port table cannot be read.
    """
    import psutil

    try:
        return {connection.laddr.port for connection in psutil.net_connections(kind="tcp4")
                if connection.status == psutil.CONN_LISTEN and connection.laddr.ip in LISTEN_HOSTS}
    except Exception as e:
        logger.warning(f"could not read the listening ports, so emulators are dialled as usual: {e}")
        return None


def dialling_only_listening(original, read_ports):
    """Wrap `DeviceManager.adb_connect` so an emulator's address is dialled only while its port is listening.

    Not dialling still checks adb's own device list, so an emulator adb already holds is found.

    Args:
        original: The framework's `adb_connect`.
        read_ports: Reads the listening ports, as `listening_ports` does.

    Returns:
        The wrapped method.
    """
    def adb_connect(self, addr, try_connect=True):
        if try_connect and str(addr).startswith(LOOPBACK):
            ports = read_ports()
            port = str(addr)[len(LOOPBACK):]
            if ports is not None and port.isdigit() and int(port) not in ports:
                try_connect = False
        return original(self, addr, try_connect)

    return adb_connect


def emulator_exes(processes):
    """Yield the executable of every running emulator, reading a path only for a process whose name is an emulator's.

    Upstream reads every process's command line instead, ~0.5s a Refresh on psutil 6 against ~5ms for the names.

    Args:
        processes: Processes as `psutil.process_iter(["name"])` yields them.

    Yields:
        The full path of each running emulator executable.
    """
    from ok.alas.emulator_windows import Emulator

    for process in processes:
        if not Emulator.is_emulator(process.info.get("name") or ""):
            continue
        try:
            yield process.exe()
        except Exception:
            # Gone, or not ours to read - upstream skips those too.
            continue


def running_emulators():
    """Stand in for `EmulatorManager.iter_running_emulator`, which upstream's emulator discovery calls.

    Yields:
        The full path of each running emulator executable.
    """
    import psutil

    yield from emulator_exes(psutil.process_iter(["name"]))


def pc_first(self):
    """Stand in for `DeviceManager.get_devices`, listing the PC game window first.

    The dropdown and `set_preferred_device(index=...)` both read this order, so they stay in step.

    Args:
        self: The `DeviceManager`.

    Returns:
        The known devices, PC window first.
    """
    return sorted(self.device_dict.values(), key=lambda device: device.get("device") != "windows")


def falling_back_to_pc(original):
    """Wrap `DeviceManager.set_preferred_device` so a missing pick falls back to the PC window instead of an emulator.

    A pick that is still listed, or one made by index from the dropdown, is left alone.

    Args:
        original: The framework's `set_preferred_device`.

    Returns:
        The wrapped method.
    """
    def set_preferred_device(self, imei=None, index=-1):
        if index == -1 and (imei or self.config.get("preferred")) not in self.device_dict:
            imei = next((device["imei"] for device in self.device_dict.values() if device.get("device") == "windows"), imei)
        return original(self, imei, index)

    return set_preferred_device


def apply():
    """List and fall back to the PC window first, dial only listening emulators, and find running ones by name."""
    global _patched
    if _patched:
        return
    from ok.alas.emulator_windows import EmulatorManager
    from ok.device.DeviceManager import DeviceManager

    DeviceManager.get_devices = pc_first
    DeviceManager.set_preferred_device = falling_back_to_pc(DeviceManager.set_preferred_device)
    DeviceManager.adb_connect = dialling_only_listening(DeviceManager.adb_connect, listening_ports)
    EmulatorManager.iter_running_emulator = staticmethod(running_emulators)
    _patched = True
    logger.info("PC window listed first and used when the saved pick is gone, emulators dialled only while listening")
