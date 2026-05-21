from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from momentum.ui.capture.accessibility import _accessible
class LibraryRow(QFrame):
    def __init__(self, sidebar: LibrarySidebar, kind: str, value, title: str, detail: str):
        super().__init__()
        self.sidebar = sidebar
        self.kind = kind
        self.value = value
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        open_button = QPushButton(f"{title}\n{detail}")
        open_button.setObjectName("LibraryOpen")
        open_button.setToolTip("Open")
        _accessible(open_button, f"Open {title}", detail)
        open_button.setMinimumWidth(0)
        open_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        open_button.clicked.connect(lambda _checked=False: sidebar.open_capture(kind, value))
        layout.addWidget(open_button, 1)

        more = QPushButton("...")
        more.setObjectName("MoreButton")
        more.setFixedWidth(38)
        more.setToolTip("More actions")
        _accessible(more, f"More actions for {title}", "Open edit and delete actions")
        more.clicked.connect(self.open_menu)
        layout.addWidget(more)

    def open_menu(self) -> None:
        menu = QMenu(self)
        edit = menu.addAction("Edit")
        delete = menu.addAction("Delete")
        action = menu.exec(self.mapToGlobal(self.rect().bottomRight()))
        if action == edit:
            self.sidebar.open_capture(self.kind, self.value)
        elif action == delete:
            self.sidebar.remove_capture(self.kind, self.value)

class TrashRow(QFrame):
    def __init__(self, sidebar: LibrarySidebar, trash_id: int, title: str, detail: str):
        super().__init__()
        self.sidebar = sidebar
        self.trash_id = trash_id
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        label = QLabel(f"{title}\n{detail}")
        _accessible(label, f"Trash item {title}", detail)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        layout.addWidget(label, 1)

        more = QPushButton("...")
        more.setObjectName("MoreButton")
        more.setFixedWidth(38)
        more.setToolTip("More actions")
        _accessible(more, f"More actions for deleted item {title}", "Open restore and delete forever actions")
        more.clicked.connect(self.open_menu)
        layout.addWidget(more)

    def open_menu(self) -> None:
        menu = QMenu(self)
        restore = menu.addAction("Restore")
        delete = menu.addAction("Delete Forever")
        action = menu.exec(self.mapToGlobal(self.rect().bottomRight()))
        if action == restore:
            self.sidebar.restore_trash(self.trash_id)
        elif action == delete:
            self.sidebar.delete_trash(self.trash_id)

class ActionRow(QFrame):
    def __init__(self, title: str, detail: str, action):
        super().__init__()
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)
        body = QVBoxLayout()
        label = QLabel(title)
        label.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        meta.setWordWrap(True)
        body.addWidget(label)
        body.addWidget(meta)
        layout.addLayout(body, 1)
        run = QPushButton("Run")
        run.setObjectName("Primary")
        _accessible(run, f"Run {title}", detail)
        run.clicked.connect(action)
        layout.addWidget(run)

class StaticLibraryRow(QFrame):
    def __init__(self, title: str, detail: str):
        super().__init__()
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        label = QLabel(title)
        label.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        meta.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(meta)
