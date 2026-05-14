from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from momentum.core.analytics import DONE, SKIPPED, goal_streak
from momentum.core.dates import days_back
from momentum.data.repository import MISSED
from momentum.state.store import AppStore
from momentum.ui.widgets.cards import Card
from momentum.ui.widgets.controls import AnimatedCheck, PillButton
from momentum.ui.widgets.dialogs import prompt_text
from momentum.ui.widgets.heatmap import GoalHeatmap, HeatCell


class GoalsView(QWidget):
    def __init__(self, store: AppStore, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QVBoxLayout()
        heading = QLabel("Goals")
        heading.setObjectName("SectionTitle")
        sub = QLabel("Long-term consistency habits")
        sub.setObjectName("Muted")
        title.addWidget(heading)
        title.addWidget(sub)
        header.addLayout(title)
        header.addStretch()
        self.add_button = PillButton("Add Goal")
        self.add_button.clicked.connect(self.focus_input)
        header.addWidget(self.add_button)
        layout.addLayout(header)

        add_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Add a recurring habit...")
        self.input.returnPressed.connect(self.add_goal)
        button = PillButton("+")
        button.clicked.connect(self.add_goal)
        add_row.addWidget(self.input, 1)
        add_row.addWidget(button)
        layout.addLayout(add_row)

        self.list = QVBoxLayout()
        self.list.setSpacing(12)
        layout.addLayout(self.list)

    def focus_input(self) -> None:
        self.input.setFocus(Qt.ShortcutFocusReason)

    def add_goal(self) -> None:
        text = self.input.text().strip()
        if text:
            self.store.add_goal(text)
            self.input.clear()

    def refresh(self) -> None:
        clear_layout(self.list)
        goals = self.store.repo.active_goals()
        if not goals:
            empty = QLabel("Add one recurring habit to start building a history.")
            empty.setObjectName("Muted")
            self.list.addWidget(empty)
            return
        logs = {
            (log.goal_id, log.day): log
            for log in self.store.repo.goal_logs(self.store.selected_day - timedelta(days=90), self.store.selected_day)
        }
        for goal in goals:
            self.list.addWidget(GoalCard(self.store, goal, logs))


class GoalCard(Card):
    def __init__(self, store: AppStore, goal, logs, parent=None):
        super().__init__("GoalCard", parent)
        self.store = store
        self.goal = goal
        self.logs = logs
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        top = QHBoxLayout()
        status = self.store.repo.goal_status(goal.id, self.store.selected_day)
        self.check = AnimatedCheck(status == DONE)
        self.check.toggled.connect(lambda _checked: self.store.toggle_goal(goal.id))
        top.addWidget(self.check)
        copy = QVBoxLayout()
        title = QLabel(goal.title)
        title.setStyleSheet("font-size: 16px; font-weight: 650;")
        meta = QLabel(f"{goal_streak(goal.id, logs, self.store.selected_day)} day consistency")
        meta.setObjectName("Muted")
        copy.addWidget(title)
        copy.addWidget(meta)
        top.addLayout(copy, 1)
        notes = QPushButton("Notes")
        notes.setObjectName("Ghost")
        notes.clicked.connect(self.add_note)
        top.addWidget(notes)
        layout.addLayout(top)

        line = QHBoxLayout()
        label = QLabel("CONSISTENCY MAP")
        label.setObjectName("Caption")
        label2 = QLabel("Last 21 days")
        label2.setObjectName("Muted")
        line.addWidget(label)
        line.addStretch()
        line.addWidget(label2)
        layout.addLayout(line)

        self.heatmap = GoalHeatmap()
        self.heatmap.set_cells(self.cells())
        self.heatmap.day_context_requested.connect(self.open_heatmap_menu)
        layout.addWidget(self.heatmap)

    def cells(self) -> list[HeatCell]:
        cells = []
        for day in days_back(21, self.store.selected_day):
            log = self.logs.get((self.goal.id, day))
            if log and log.status == DONE:
                cells.append(HeatCell(day, 100, DONE, log.note))
            elif log and log.status == SKIPPED:
                cells.append(HeatCell(day, 0, SKIPPED, log.note))
            elif log:
                cells.append(HeatCell(day, 0, MISSED, log.note))
            else:
                cells.append(HeatCell(day, 0, ""))
        return cells

    def open_menu(self, point) -> None:
        self._menu(self.mapToGlobal(point)).exec(self.mapToGlobal(point))

    def open_heatmap_menu(self, day, global_point) -> None:
        self.store.set_day(day)
        self._menu(global_point).exec(global_point)

    def _menu(self, global_point):
        menu = QMenu(self)
        menu.addAction("Add note", self.add_note)
        menu.addAction("Edit", self.edit_goal)
        menu.addAction("Mark skipped", lambda: self.store.skip_goal(self.goal.id))
        menu.addSeparator()
        menu.addAction("Archive", lambda: self.store.archive_goal(self.goal.id))
        return menu

    def add_note(self) -> None:
        note = prompt_text("Goal Note", f"Note for {self.goal.title}", multiline=True, parent=self)
        if note is not None:
            self.store.add_goal_note(self.goal.id, note)

    def edit_goal(self) -> None:
        title = prompt_text("Edit Goal", "Goal name", self.goal.title, parent=self)
        if title:
            self.store.edit_goal(self.goal.id, title)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.deleteLater()
        child = item.layout()
        if child:
            clear_layout(child)
