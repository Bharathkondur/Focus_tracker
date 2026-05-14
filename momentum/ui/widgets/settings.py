from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from momentum import __version__
from momentum.data.paths import APP_ICON_PATH, BASE_DIR, DB_PATH


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        subtitle = QLabel("Momentum stays local-first. Your data lives on this machine.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(self.row("Version", __version__))
        layout.addWidget(self.row("Database", str(DB_PATH)))
        layout.addWidget(self.row("App folder", str(BASE_DIR)))
        layout.addWidget(self.row("App icon", str(APP_ICON_PATH)))

        actions = QHBoxLayout()
        open_folder = QPushButton("Open App Folder")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE_DIR))))
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        actions.addWidget(open_folder)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)

    def row(self, label: str, value: str):
        wrap = QLabel(f"<b>{label}</b><br><span style='color:#94A3B8'>{value}</span>")
        wrap.setTextInteractionFlags(wrap.textInteractionFlags() | Qt.TextSelectableByMouse)
        wrap.setWordWrap(True)
        return wrap
