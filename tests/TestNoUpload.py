"""Check that nothing this fork runs can send a config to upstream's pool."""

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import config  # noqa: E402
from src.en import upload  # noqa: E402

# The settings row as the two modes declare it, in upstream's order.
BUTTONS = ["导入配置码", "导出配置码", "热门配置", "保存配置", "切换配置"]


class FakeTask:
    """A mode, holding only the settings the patch edits."""

    def __init__(self, buttons=None):
        if buttons is None:
            buttons = BUTTONS
        self.config_type = {
            upload.BUTTONS_KEY: {"type": "button", "buttons": [{"text": text} for text in buttons]},
            "游戏语言": {"type": "drop_down", "options": ["简体中文"]},
        }

    def button_texts(self):
        return [button["text"] for button in self.config_type[upload.BUTTONS_KEY]["buttons"]]


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

    def test_the_popular_config_button_is_removed(self):
        task = FakeTask()
        self.assertTrue(upload.drop_hot_config_button(task))
        self.assertNotIn("热门配置", task.button_texts())

    def test_the_other_config_buttons_are_left_alone(self):
        """Import, export, save and switch are all local, so they stay."""
        task = FakeTask()
        upload.drop_hot_config_button(task)
        self.assertEqual(["导入配置码", "导出配置码", "保存配置", "切换配置"], task.button_texts())

    def test_a_task_with_no_buttons_is_left_alone(self):
        task = FakeTask(buttons=[])
        self.assertFalse(upload.drop_hot_config_button(task))

    def test_removing_twice_changes_nothing(self):
        task = FakeTask()
        upload.drop_hot_config_button(task)
        self.assertFalse(upload.drop_hot_config_button(task))
        self.assertEqual(4, len(task.button_texts()))

    def test_the_upload_setting_is_gone_from_the_settings_tab(self):
        """Leaving it there would be the wrong fix anyway: the gates below it default to on when it is absent."""
        names = [option.name for option in config["global_configs"]]
        self.assertNotIn("配置上传", names)
        self.assertEqual(["OCR设置"], names)


if __name__ == "__main__":
    unittest.main()
