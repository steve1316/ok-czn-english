"""Check that nothing this fork runs can send a config to upstream's pool."""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import config  # noqa: E402
from src.en import upload  # noqa: E402


class FakeTask:
    """A mode, holding only the settings the patch edits."""

    def __init__(self):
        self.default_config = {upload.ROW_KEY: "", "游戏语言": ""}
        self.config_type = {upload.ROW_KEY: {"type": "button"}, "游戏语言": {"type": "drop_down"}}


def fake_sync_module():
    """Build a stand-in for `ok_tasks/config_sync.py`, wired the way upstream wires it.

    `check_upload_if_needed` is written the way upstream writes it, calling `upload_config` by name out of its
    own module rather than through a reference, which is the property the patch depends on.

    Returns:
        The module, already in `sys.modules` under the name the patch looks for.
    """
    module = types.ModuleType(upload.SYNC_MODULE)
    sent = []

    def upload_config(task, mode):
        sent.append(mode)
        return True

    def check_upload_if_needed(task, mode):
        return module.upload_config(task, mode)

    module.upload_config = upload_config
    module.check_upload_if_needed = check_upload_if_needed
    module.sent = sent
    sys.modules[upload.SYNC_MODULE] = module
    return module


class TestNoUpload(unittest.TestCase):

    def setUp(self):
        upload._upload_stopped = False
        self.module = fake_sync_module()

    def tearDown(self):
        upload._upload_stopped = False
        sys.modules.pop(upload.SYNC_MODULE, None)

    def test_the_upload_is_refused(self):
        self.assertTrue(upload.stop_uploading())
        self.assertFalse(self.module.upload_config(FakeTask(), "chaos"))
        self.assertEqual([], self.module.sent)

    def test_the_mode_own_caller_cannot_route_around_it(self):
        """The modes import `check_upload_if_needed` directly, so that name is the wrong one to patch."""
        caller = self.module.check_upload_if_needed
        upload.stop_uploading()
        self.assertFalse(caller(FakeTask(), "chaos"))
        self.assertEqual([], self.module.sent)

    def test_stopping_twice_is_reported_once(self):
        self.assertTrue(upload.stop_uploading())
        self.assertFalse(upload.stop_uploading())

    def test_a_module_that_is_not_loaded_yet_is_not_an_error(self):
        """The modes join `sys.path` after the framework's loader runs, so absence is the normal early case."""
        sys.modules.pop(upload.SYNC_MODULE, None)
        self.assertFalse(upload.stop_uploading())

    def test_the_configuration_row_is_removed(self):
        # Popping only the form's half would leave the key in every saved config, and only the default's half would leave the buttons.
        task = FakeTask()
        upload.remove_config_row(task)
        self.assertEqual(({"游戏语言": ""}, ["游戏语言"]), (task.default_config, list(task.config_type)))

    def test_the_upload_setting_is_gone_from_the_settings_tab(self):
        """Leaving it there would be the wrong fix anyway: the gates below it default to on when it is absent."""
        names = [option.name for option in config["global_configs"]]
        self.assertNotIn("配置上传", names)
        self.assertEqual(["OCR设置", "auto_analysis", "Input Variance"], names)


if __name__ == "__main__":
    unittest.main()
