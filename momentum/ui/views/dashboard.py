from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from momentum.core.dates import greeting, header_day
from momentum.state.store import AppStore
from momentum.ui.views.goals import GoalsView
from momentum.ui.views.insights import InsightsView
from momentum.ui.views.reflection import ReflectionView
from momentum.ui.views.tasks import TasksView
from momentum.ui.widgets.controls import PillButton


class Dashboard(QWidget):
    def __init__(self, store: AppStore, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        title = QVBoxLayout()
        self.date_label = QLabel()
        self.date_label.setObjectName("Caption")
        hero = QLabel(greeting())
        hero.setObjectName("Hero")
        title.addWidget(self.date_label)
        title.addWidget(hero)
        header.addLayout(title, 1)
        self.prev = QPushButton("<")
        self.prev.clicked.connect(self.store.previous_day)
        self.today = QPushButton("Today")
        self.today.clicked.connect(self.store.go_today)
        self.next = QPushButton(">")
        self.next.clicked.connect(self.store.next_day)
        review = PillButton("Review Day", primary=True)
        review.clicked.connect(lambda: self.reflection.save())
        for button in (self.prev, self.today, self.next, review):
            header.addWidget(button)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 8, 0)
        self.content_layout.setSpacing(28)
        self.goals = GoalsView(store)
        self.tasks = TasksView(store)
        self.reflection = ReflectionView(store)
        self.insights = InsightsView(store)
        self.content_layout.addWidget(self.goals)
        self.content_layout.addWidget(self.tasks)
        self.content_layout.addWidget(self.reflection)
        self.content_layout.addWidget(self.insights)
        self.content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def refresh(self) -> None:
        self.date_label.setText(header_day(self.store.selected_day))
        self.goals.refresh()
        self.tasks.refresh()
        self.reflection.refresh()
        self.insights.refresh()

    def refresh_data(self) -> None:
        self.goals.refresh()
        self.tasks.refresh()
        self.insights.refresh()
