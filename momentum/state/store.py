from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QObject, Signal

from momentum.core.dates import clamp_to_today, today
from momentum.core.models import Reflection
from momentum.data.repository import DONE, MISSED, OPEN, SKIPPED, Repository


class AppStore(QObject):
    day_changed = Signal()
    data_changed = Signal()

    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.selected_day = today()

    def set_day(self, day: date) -> None:
        new_day = clamp_to_today(day)
        if new_day == self.selected_day:
            return
        self.selected_day = new_day
        self.day_changed.emit()

    def previous_day(self) -> None:
        self.set_day(self.selected_day - timedelta(days=1))

    def next_day(self) -> None:
        self.set_day(self.selected_day + timedelta(days=1))

    def go_today(self) -> None:
        self.set_day(today())

    def add_goal(self, title: str) -> None:
        if title.strip():
            self.repo.add_goal(title.strip(), created_on=self.selected_day)
            self.data_changed.emit()

    def toggle_goal(self, goal_id: int) -> None:
        current = self.repo.goal_status(goal_id, self.selected_day)
        self.repo.set_goal_status(goal_id, self.selected_day, MISSED if current == DONE else DONE)
        self.data_changed.emit()

    def skip_goal(self, goal_id: int) -> None:
        self.repo.set_goal_status(goal_id, self.selected_day, SKIPPED)
        self.data_changed.emit()

    def add_goal_note(self, goal_id: int, note: str) -> None:
        self.repo.set_goal_log_note(goal_id, self.selected_day, note)
        self.data_changed.emit()

    def edit_goal(self, goal_id: int, title: str) -> None:
        if title.strip():
            self.repo.update_goal_title(goal_id, title.strip())
            self.data_changed.emit()

    def archive_goal(self, goal_id: int) -> None:
        self.repo.archive_goal(goal_id, self.selected_day)
        self.data_changed.emit()

    def add_task(self, title: str, carry_forward: bool = False, planned_time: str = "") -> None:
        if title.strip():
            self.repo.add_task(title.strip(), self.selected_day, carry_forward, planned_time)
            self.data_changed.emit()

    def toggle_task(self, task_id: int) -> None:
        task = self.repo.task(task_id)
        self.repo.set_task_status(task_id, OPEN if task.status == DONE else DONE)
        self.data_changed.emit()

    def skip_task(self, task_id: int) -> None:
        self.repo.set_task_status(task_id, SKIPPED)
        self.data_changed.emit()

    def add_task_note(self, task_id: int, note: str) -> None:
        self.repo.set_task_note(task_id, note)
        self.data_changed.emit()

    def edit_task(self, task_id: int, title: str) -> None:
        if title.strip():
            self.repo.update_task_title(task_id, title.strip())
            self.data_changed.emit()

    def set_task_time(self, task_id: int, planned_time: str) -> None:
        self.repo.update_task_time(task_id, planned_time)
        self.data_changed.emit()

    def archive_task(self, task_id: int) -> None:
        self.repo.archive_task(task_id)
        self.data_changed.emit()

    def save_reflection(self, mood: str, energy: int, note: str, short_reflection: str) -> None:
        self.repo.save_reflection(
            Reflection(
                day=self.selected_day,
                mood=mood,
                energy=energy,
                note=note,
                short_reflection=short_reflection,
                is_vacation=self.repo.reflection(self.selected_day).is_vacation,
            )
        )
        self.data_changed.emit()

    def mark_vacation_day(self, enabled: bool = True) -> None:
        self.repo.mark_vacation(self.selected_day, enabled)
        self.data_changed.emit()
