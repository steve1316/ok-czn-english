"""The About page's Sponsor link, which shows the author's reward codes rather than opening a web page."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ok import og
from ok.ui.qt.about.AboutTab import AboutTab
from ok.ui.qt.kit.labels import Label
from ok.ui.qt.kit.theme import theme
from ok.util.file import get_path_relative_to_exe


class SponsorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sponsorDialog")
        self.setWindowTitle(og.app.tr("赞赏支持"))
        self.setMinimumWidth(720)
        self.setStyleSheet(
            f"QDialog#sponsorDialog {{ background-color: {theme.color('window').name()}; }}"
            f"QDialog#sponsorDialog QLabel {{ color: {theme.color('text').name()}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        title = Label(og.app.tr("赞赏支持"), "subtitle", self)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = Label(og.app.tr("如果喜欢这个工具，可以赞赏up主持续开发~感谢"), parent=self)
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        codes_layout = QHBoxLayout()
        codes_layout.setSpacing(24)
        codes_layout.addWidget(self._create_code(og.app.tr("微信赞赏"), "docs/images/wechat_reward_code.png"))
        codes_layout.addWidget(self._create_code(og.app.tr("支付宝赞赏"), "docs/images/alipay_reward_code.png"))
        layout.addLayout(codes_layout)

    def _create_code(self, title: str, relative_path: str) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        image = QLabel(container)
        image.setAlignment(Qt.AlignCenter)
        image_path = Path(get_path_relative_to_exe(relative_path))
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            image.setText(f"Could not load the image: {image_path}")
        else:
            image.setPixmap(pixmap.scaled(300, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(image)

        caption = Label(title, parent=container)
        caption.setAlignment(Qt.AlignCenter)
        layout.addWidget(caption)
        return container


def install_sponsor_dialog():
    """Have the About page's Sponsor link open the dialog, since its `local` URL is not a real address."""
    if getattr(AboutTab, "_ok_kes_sponsor_installed", False):
        return

    original_open_link = AboutTab.open_link

    def open_link(about_tab, key):
        if key == "sponsor":
            SponsorDialog(about_tab.window()).exec()
            return
        original_open_link(about_tab, key)

    AboutTab.open_link = open_link
    AboutTab._ok_kes_sponsor_installed = True
