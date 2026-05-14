from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from momentum.data.repository import DONE, SKIPPED
from momentum.state.store import AppStore
from momentum.ui.widgets.cards import Card
from momentum.ui.widgets.controls import AnimatedCheck, PillButton
from momentum.ui.widgets.dialogs import prompt_text
from momentum.ui.views.goals import clear_layout


class TasksView(QWidget):
    def __init__(self, store: AppStore, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QVBoxLayout()
        heading = QLabel("Daily Tasks")
        heading.setObjectName("SectionTitle")
        sub = QLabel("Operational tasks for the selected day")
        sub.setObjectName("Muted")
        title.addWidget(heading)
        title.addWidget(sub)
        header.addLayout(title)
        header.addStretch()
        self.add_button = PillButton("Add Task")
        self.add_button.clicked.connect(self.focus_input)
        header.addWidget(self.add_button)
        layout.addLayout(header)

        add_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Add a task for today...")
        self.input.returnPressed.connect(self.add_task)
        self.time_input = QLineEdit()
        self.time_input.setPlaceholderText("HH:MM")
        self.time_input.setFixedWidth(92)
        self.time_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"^([01]?\d|2[0-3]):[0-5]\d$|^$")))
        self.time_input.returnPressed.connect(self.add_task)
        self.carry = QCheckBox("Carry if unfinished")
        button = PillButton("+")
        button.clicked.connect(self.add_task)
        add_row.addWidget(self.input, 1)
        add_row.addWidget(self.time_input)
        add_row.addWidget(self.carry)
        add_row.addWidget(button)
        layout.addLayout(add_row)

        self.list = QVBoxLayout()
        self.list.setSpacing(9)
        layout.addLayout(self.list)

    def focus_input(self) -> None:
        self.input.setFocus(Qt.ShortcutFocusReason)

    def add_task(self) -> None:
        text = self.input.text().strip()
        if text:
            self.store.add_task(text, self.carry.isChecked(), self.time_input.text().strip())
            self.input.clear()
            self.time_input.clear()

    def refresh(self) -> None:
        clear_layout(self.list)
        tasks = self.store.repo.tasks_for_day(self.store.selected_day)
        if not tasks:
            empty = QLabel("No daily tasks yet. Keep this list short and operational.")
            empty.setObjectName("Muted")
            self.list.addWidget(empty)
            return
        for task in tasks:
            self.list.addWidget(TaskRow(self.store, task))


class TaskRow(Card):
    def __init__(self, store: AppStore, task, parent=None):
        super().__init__("TaskRow", parent)
        self.store = store
        self.task = task
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        check = AnimatedCheck(task.status == DONE, square=True)
        check.toggled.connect(lambda _checked: self.store.toggle_task(task.id))
        layout.addWidget(check)
        title = QLabel(task.title)
        if task.status == SKIPPED:
            title.setStyleSheet("color: #64748B;")
        layout.addWidget(title, 1)
        if task.planned_time:
            time_badge = QLabel(task.planned_time)
            time_badge.setObjectName("Muted")
            layout.addWidget(time_badge)
        if task.carry_forward:
            badge = QLabel("carry")
            badge.setObjectName("Muted")
            layout.addWidget(badge)
        more = QPushButton("...")
        more.setObjectName("Ghost")
        more.clicked.connect(lambda: self._menu().exec(more.mapToGlobal(more.rect().bottomLeft())))
        layout.addWidget(more)

    def open_menu(self, point) -> None:
        self._menu().exec(self.mapToGlobal(point))

    def _menu(self):
        menu = QMenu(self)
        menu.addAction("Add note", self.add_note)
        menu.addAction("Set time", self.set_time)
        menu.addAction("Edit", self.edit_task)
        menu.addAction("Mark skipped", lambda: self.store.skip_task(self.task.id))
        menu.addSeparator()
        menu.addAction("Archive", lambda: self.store.archive_task(self.task.id))
        return menu

    def add_note(self) -> None:
        note = prompt_text("Task Note", f"Note for {self.task.title}", self.task.note, True, self)
        if note is not None:
            self.store.add_task_note(self.task.id, note)

    def edit_task(self) -> None:
        title = prompt_text("Edit Task", "Task name", self.task.title, parent=self)
        if title:
            self.store.edit_task(self.task.id, title)

    def set_time(self) -> None:
        planned_time = prompt_text("Task Time", "Plan time as HH:MM", self.task.planned_time, parent=self)
        if planned_time is not None:
            self.store.set_task_time(self.task.id, planned_time)
