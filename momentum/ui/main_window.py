from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QWidget
from PySide6.QtGui import QIcon

from momentum.data.paths import APP_ICON_PATH
from momentum.state.store import AppStore
from momentum.ui.sidebar import Sidebar
from momentum.ui.views.dashboard import Dashboard


class MainWindow(QMainWindow):
    def __init__(self, store: AppStore):
        super().__init__()
        self.store = store
        self.setWindowTitle("Momentum")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1280, 820)
        self.setMinimumSize(1080, 720)

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar(store)
        self.dashboard = Dashboard(store)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.dashboard, 1)
        self.setCentralWidget(root)

        store.day_changed.connect(self.refresh)
        store.data_changed.connect(self.refresh_data)
        self.refresh()

    def refresh(self) -> None:
        self.sidebar.refresh()
        self.dashboard.refresh()

    def refresh_data(self) -> None:
        self.sidebar.refresh()
        self.dashboard.refresh_data()
