"""Stop the fork sending anything to upstream's shared config pool, and remove the modes' Configuration row.

Upstream's modes post their config to a CN community pool and show a row of buttons that share and swap configs.
A Global client's entries are noise in that pool, and this fork does not offer the row.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# The module in `ok_tasks/` that does the uploading, and the one function in it that reaches the network to
# send. `fetch_popular_configs` also reaches the network, but only the Configuration row calls it.
SYNC_MODULE = "config_sync"
UPLOAD = "upload_config"

# The Configuration row, declared by Chaos and Sortie. A saved config holding this key loses it the next time it loads.
ROW_KEY = "配置操作"

_patched = False
_upload_stopped = False


def refuse_upload(task, mode):
    """Stand in for `config_sync.upload_config`, which posts the config to upstream's database.

    Upstream sends the whole config, the win rate, and a machine id hashed from the MAC address, the hostname
    and the Windows user name. Refusing here is what makes it definitive: `check_upload_if_needed` looks this
    name up in its own module when it fires, so the mode's own import of that caller cannot route around it.

    Args:
        task: The running task, ignored.
        mode: The mode name upstream would have filed the config under, ignored.

    Returns:
        False, the value upstream uses for an upload that did not happen.
    """
    return False


def stop_uploading():
    """Replace the upload once the module holding it has been imported.

    Returns:
        True once the replacement is in place, so it is only reported the first time.
    """
    global _upload_stopped
    if _upload_stopped:
        return False
    import sys

    # Not imported here. The modes are only on `sys.path` after the framework's loader has put them there,
    # and importing this early would either raise or pull it in ahead of that loader.
    module = sys.modules.get(SYNC_MODULE)
    if module is None or not hasattr(module, UPLOAD):
        return False
    setattr(module, UPLOAD, refuse_upload)
    _upload_stopped = True
    return True


def remove_config_row(task):
    """Take the Configuration row out of a mode's settings.

    Args:
        task: The task whose settings are being built, before its saved config is read.
    """
    task.default_config.pop(ROW_KEY, None)
    task.config_type.pop(ROW_KEY, None)


def apply():
    """Refuse the upload and remove the Configuration row, as each task is set up."""
    global _patched
    if _patched:
        return
    try:
        from ok.task.task import BaseTask
    except ImportError:
        logger.warning("could not import BaseTask, the config upload is left as upstream has it")
        return

    original_load_config = BaseTask.load_config

    def patched_load_config(self):
        # By now the task is fully built, so its settings are there to edit, and the module it imported is in
        # `sys.modules`. Both are false while this module is being read.
        try:
            if stop_uploading():
                logger.info("config upload refused, nothing is sent to the upstream pool")
            remove_config_row(self)
        except Exception as error:
            logger.warning(f"could not turn off the config upload or row for {self.__class__.__name__}: {error}")
        original_load_config(self)

    BaseTask.load_config = patched_load_config
    _patched = True
