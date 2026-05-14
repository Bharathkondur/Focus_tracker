from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(slots=True)
class Goal:
    id: int
    title: str
    cadence: str
    color: str
    created_on: date
    archived_on: date | None = None
    sort_order: int = 0
    note: str = ""

    @property
    def active(self) -> bool:
        return self.archived_on is None


@dataclass(slots=True)
class GoalLog:
    goal_id: int
    day: date
    status: str
    intensity: int = 0
    note: str = ""
    updated_at: datetime | None = None


@dataclass(slots=True)
class DailyTask:
    id: int
    title: str
    day: date
    status: str
    planned_time: str = ""
    carry_forward: bool = False
    note: str = ""
    created_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class Reflection:
    day: date
    mood: str = ""
    energy: int = 3
    note: str = ""
    short_reflection: str = ""
    is_vacation: bool = False
    updated_at: datetime | None = None


@dataclass(slots=True)
class DayScore:
    day: date
    total: int
    completed: int
    skipped: int = 0
    vacation: bool = False

    @property
    def percent(self) -> int:
        trackable = self.total - self.skipped
        if self.vacation or trackable <= 0:
            return 0
        return round((self.completed / trackable) * 100)
