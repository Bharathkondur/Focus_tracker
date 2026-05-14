from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout


class TextPrompt(QDialog):
    def __init__(self, title: str, label: str, value: str = "", multiline: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setObjectName("PromptDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        heading = QLabel(label)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        if multiline:
            self.input = QTextEdit()
            self.input.setPlainText(value)
            self.input.setMinimumHeight(120)
        else:
            self.input = QLineEdit(value)
        layout.addWidget(self.input)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("Primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def text(self) -> str:
        if isinstance(self.input, QTextEdit):
            return self.input.toPlainText().strip()
        return self.input.text().strip()


def prompt_text(title: str, label: str, value: str = "", multiline: bool = False, parent=None) -> str | None:
    dialog = TextPrompt(title, label, value, multiline, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.text()
    return None
