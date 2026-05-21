from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDateEdit, QLineEdit, QListWidget, QPushButton, QTextEdit, QWidget


FOCUSABLE_WIDGETS = (QDateEdit, QLineEdit, QListWidget, QPushButton, QTextEdit)


def _accessible(widget: QWidget, name: str, description: str = "") -> None:
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    if isinstance(widget, FOCUSABLE_WIDGETS) and widget.focusPolicy() == Qt.NoFocus:
        widget.setFocusPolicy(Qt.StrongFocus)
