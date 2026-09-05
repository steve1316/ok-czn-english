"""Stop the fork sending anything to upstream's shared config pool.

The pool is the upstream CN community's, so a Global client's entries are noise in it either way.
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# The module in `ok_tasks/` that does the uploading, and the one function in it that reaches the network to
# send. `fetch_popular_configs` also reaches the network, but only the browser button calls it.
SYNC_MODULE = "config_sync"
UPLOAD = "upload_config"

# The settings row of buttons each mode shows, and the one that opens the popular-config browser.
BUTTONS_KEY = "配置操作"
HOT_CONFIGS = "热门配置"

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


def drop_hot_config_button(task):
    """Take the popular-config button out of a mode's settings.

    It downloads other players' configs, which are written against the CN client and name Chinese cards that
    this fork's OCR can never read. It also refuses to open at all unless uploading is switched on.

    Args:
        task: The task whose settings are being built.

    Returns:
        True when a button was removed.
    """
    buttons = (task.config_type or {}).get(BUTTONS_KEY, {}).get("buttons")
    if not buttons:
        return False
    kept = [button for button in buttons if button.get("text") != HOT_CONFIGS]
    if len(kept) == len(buttons):
        return False
    task.config_type[BUTTONS_KEY]["buttons"] = kept
    return True


def apply():
    """Refuse the upload and drop the button that depends on it, as each task is set up."""
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
            if drop_hot_config_button(self):
                logger.info(f"removed the popular-config button from {self.__class__.__name__}")
        except Exception as error:
            logger.warning(f"could not turn off the config upload for {self.__class__.__name__}: {error}")
        original_load_config(self)

    BaseTask.load_config = patched_load_config
    _patched = True
