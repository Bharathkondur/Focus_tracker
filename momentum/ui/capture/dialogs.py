from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from momentum.core.dates import today
from momentum.ui.capture.accessibility import _accessible


class CommandPalette(QDialog):
    def __init__(self, window: CaptureWindow):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Command Palette")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command or capture text...")
        layout.addWidget(self.input)
        commands = [
            ("New Today Note", lambda: window.open_note_day(today())),
            ("Focus Mode", window.toggle_focus_mode),
            ("Support Settings", window.open_support_settings),
            ("Create Backup", window.create_database_backup),
            ("Export Database", window.export_database_sql),
            ("Export Support Bundle", window.export_support_bundle),
            ("Open Data Folder", window.open_data_folder),
            ("Export Standup", window.export_standup),
            ("Export Engineering Report", window.export_engineering_report),
            ("Open Trash", lambda: window.library.set_mode("trash")),
            ("Open Projects", lambda: window.library.set_mode("project")),
        ]
        for label, action in commands:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=action: self._run(fn))
            layout.addWidget(button)
        self.input.returnPressed.connect(self.capture_text)

    def _run(self, action) -> None:
        action()
        self.accept()

    def capture_text(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.window.capture.input.setPlainText(text)
        self.window.submit()
        self.accept()


class SupportSettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Support Settings")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Support Settings")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        detail = QLabel("Create local backups, exports, and support bundles without sending anything online.")
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        actions = [
            ("Create Backup", window.create_database_backup),
            ("Export Database", window.export_database_sql),
            ("Export Support Bundle", window.export_support_bundle),
            ("Open Data Folder", window.open_data_folder),
        ]
        for label, action in actions:
            button = QPushButton(label)
            _accessible(button, label)
            button.clicked.connect(lambda _checked=False, fn=action: self._run(fn))
            layout.addWidget(button)

        close = QPushButton("Close")
        _accessible(close, "Close support settings")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _run(self, action) -> None:
        action()
