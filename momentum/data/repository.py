from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlite3 import Row

from momentum.core.dates import date_key, parse_day, today
from momentum.core.models import DailyTask, DayScore, Goal, GoalLog, Reflection


DONE = "done"
MISSED = "missed"
SKIPPED = "skipped"
OPEN = "open"
ARCHIVED = "archived"


class Repository:
    def __init__(self, conn):
        self.conn = conn

    def active_goals(self) -> list[Goal]:
        rows = self.conn.execute(
            """
            SELECT * FROM goals
            WHERE archived_on IS NULL
            ORDER BY sort_order ASC, created_on ASC, id ASC
            """
        ).fetchall()
        return [self._goal(row) for row in rows]

    def all_goals(self) -> list[Goal]:
        return [self._goal(row) for row in self.conn.execute("SELECT * FROM goals ORDER BY id").fetchall()]

    def add_goal(self, title: str, color: str = "#34D399", created_on: date | None = None) -> Goal:
        day = created_on or today()
        order = self.conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM goals").fetchone()[0]
        cur = self.conn.execute(
            "INSERT INTO goals (title, color, created_on, sort_order) VALUES (?, ?, ?, ?)",
            (title.strip(), color, date_key(day), order),
        )
        self.conn.commit()
        return self.goal(cur.lastrowid)

    def goal(self, goal_id: int) -> Goal:
        row = self.conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if row is None:
            raise KeyError(f"Goal {goal_id} does not exist")
        return self._goal(row)

    def update_goal_title(self, goal_id: int, title: str) -> None:
        self.conn.execute("UPDATE goals SET title = ? WHERE id = ?", (title.strip(), goal_id))
        self.conn.commit()

    def archive_goal(self, goal_id: int, archived_on: date | None = None) -> None:
        self.conn.execute(
            "UPDATE goals SET archived_on = ? WHERE id = ?",
            (date_key(archived_on or today()), goal_id),
        )
        self.conn.commit()

    def set_goal_note(self, goal_id: int, note: str) -> None:
        self.conn.execute("UPDATE goals SET note = ? WHERE id = ?", (note, goal_id))
        self.conn.commit()

    def goal_logs(self, start: date, end: date, goal_id: int | None = None) -> list[GoalLog]:
        params: list[object] = [date_key(start), date_key(end)]
        where = "day BETWEEN ? AND ?"
        if goal_id is not None:
            where += " AND goal_id = ?"
            params.append(goal_id)
        rows = self.conn.execute(
            f"SELECT * FROM goal_logs WHERE {where} ORDER BY day ASC",
            params,
        ).fetchall()
        return [self._goal_log(row) for row in rows]

    def set_goal_status(self, goal_id: int, day: date, status: str, note: str | None = None) -> None:
        intensity = 3 if status == DONE else 1 if status == SKIPPED else 0
        existing = self.conn.execute(
            "SELECT note FROM goal_logs WHERE goal_id = ? AND day = ?",
            (goal_id, date_key(day)),
        ).fetchone()
        final_note = existing["note"] if note is None and existing else note or ""
        self.conn.execute(
            """
            INSERT INTO goal_logs (goal_id, day, status, intensity, note, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(goal_id, day) DO UPDATE SET
                status = excluded.status,
                intensity = excluded.intensity,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (goal_id, date_key(day), status, intensity, final_note),
        )
        self.conn.commit()

    def set_goal_log_note(self, goal_id: int, day: date, note: str) -> None:
        current = self.goal_status(goal_id, day) or MISSED
        self.set_goal_status(goal_id, day, current, note)

    def goal_status(self, goal_id: int, day: date) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM goal_logs WHERE goal_id = ? AND day = ?",
            (goal_id, date_key(day)),
        ).fetchone()
        return row["status"] if row else None

    def tasks_for_day(self, day: date) -> list[DailyTask]:
        rows = self.conn.execute(
            """
            SELECT * FROM daily_tasks
            WHERE day = ? AND status != ?
            ORDER BY
                CASE WHEN planned_time = '' THEN 1 ELSE 0 END,
                planned_time ASC,
                id ASC
            """,
            (date_key(day), ARCHIVED),
        ).fetchall()
        return [self._task(row) for row in rows]

    def add_task(
        self,
        title: str,
        day: date,
        carry_forward: bool = False,
        planned_time: str = "",
    ) -> DailyTask:
        cur = self.conn.execute(
            """
            INSERT INTO daily_tasks (title, day, carry_forward, planned_time)
            VALUES (?, ?, ?, ?)
            """,
            (title.strip(), date_key(day), int(carry_forward), normalize_time(planned_time)),
        )
        self.conn.commit()
        return self.task(cur.lastrowid)

    def task(self, task_id: int) -> DailyTask:
        row = self.conn.execute("SELECT * FROM daily_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} does not exist")
        return self._task(row)

    def update_task_title(self, task_id: int, title: str) -> None:
        self.conn.execute("UPDATE daily_tasks SET title = ? WHERE id = ?", (title.strip(), task_id))
        self.conn.commit()

    def update_task_time(self, task_id: int, planned_time: str) -> None:
        self.conn.execute(
            "UPDATE daily_tasks SET planned_time = ? WHERE id = ?",
            (normalize_time(planned_time), task_id),
        )
        self.conn.commit()

    def set_task_status(self, task_id: int, status: str) -> None:
        completed = "CURRENT_TIMESTAMP" if status == DONE else "NULL"
        self.conn.execute(
            f"UPDATE daily_tasks SET status = ?, completed_at = {completed} WHERE id = ?",
            (status, task_id),
        )
        self.conn.commit()

    def archive_task(self, task_id: int) -> None:
        self.set_task_status(task_id, ARCHIVED)

    def set_task_note(self, task_id: int, note: str) -> None:
        self.conn.execute("UPDATE daily_tasks SET note = ? WHERE id = ?", (note, task_id))
        self.conn.commit()

    def carry_unfinished_tasks(self, from_day: date, to_day: date) -> int:
        rows = self.conn.execute(
            """
            SELECT title, note, carry_forward, planned_time FROM daily_tasks
            WHERE day = ? AND status = ? AND carry_forward = 1
            """,
            (date_key(from_day), OPEN),
        ).fetchall()
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO daily_tasks (title, day, note, carry_forward, planned_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["title"],
                    date_key(to_day),
                    row["note"],
                    row["carry_forward"],
                    row["planned_time"],
                ),
            )
        self.conn.commit()
        return len(rows)

    def reflection(self, day: date) -> Reflection:
        row = self.conn.execute("SELECT * FROM reflections WHERE day = ?", (date_key(day),)).fetchone()
        if row is None:
            return Reflection(day=day)
        return self._reflection(row)

    def save_reflection(self, reflection: Reflection) -> None:
        self.conn.execute(
            """
            INSERT INTO reflections (day, mood, energy, note, short_reflection, is_vacation, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(day) DO UPDATE SET
                mood = excluded.mood,
                energy = excluded.energy,
                note = excluded.note,
                short_reflection = excluded.short_reflection,
                is_vacation = excluded.is_vacation,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                date_key(reflection.day),
                reflection.mood,
                reflection.energy,
                reflection.note,
                reflection.short_reflection,
                int(reflection.is_vacation),
            ),
        )
        self.conn.commit()

    def mark_vacation(self, day: date, enabled: bool = True) -> None:
        reflection = self.reflection(day)
        reflection.is_vacation = enabled
        self.save_reflection(reflection)

    def setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def day_scores(self, start: date, end: date) -> list[DayScore]:
        goals = self.all_goals()
        logs = {(log.goal_id, log.day): log for log in self.goal_logs(start, end)}
        task_rows_by_day: dict[date, list[Row]] = {}
        task_rows = self.conn.execute(
            """
            SELECT day, status FROM daily_tasks
            WHERE day BETWEEN ? AND ? AND status != ?
            ORDER BY day ASC
            """,
            (date_key(start), date_key(end), ARCHIVED),
        ).fetchall()
        for row in task_rows:
            task_rows_by_day.setdefault(parse_day(row["day"]), []).append(row)
        reflections = {
            parse_day(row["day"]): row["is_vacation"]
            for row in self.conn.execute(
                "SELECT day, is_vacation FROM reflections WHERE day BETWEEN ? AND ?",
                (date_key(start), date_key(end)),
            )
        }
        scores = []
        day = start
        while day <= end:
            active = [
                goal for goal in goals
                if goal.created_on <= day and (goal.archived_on is None or goal.archived_on >= day)
            ]
            completed = skipped = 0
            for goal in active:
                status = logs.get((goal.id, day))
                if status and status.status == DONE:
                    completed += 1
                elif status and status.status == SKIPPED:
                    skipped += 1
            task_rows = task_rows_by_day.get(day, [])
            for row in task_rows:
                if row["status"] == DONE:
                    completed += 1
                elif row["status"] == SKIPPED:
                    skipped += 1
            scores.append(
                DayScore(
                    day=day,
                    total=len(active) + len(task_rows),
                    completed=completed,
                    skipped=skipped,
                    vacation=bool(reflections.get(day, 0)),
                )
            )
            day += timedelta(days=1)
        return scores

    def _goal(self, row: Row) -> Goal:
        return Goal(
            id=row["id"],
            title=row["title"],
            cadence=row["cadence"],
            color=row["color"],
            created_on=parse_day(row["created_on"]),
            archived_on=parse_day(row["archived_on"]) if row["archived_on"] else None,
            sort_order=row["sort_order"],
            note=row["note"],
        )

    def _goal_log(self, row: Row) -> GoalLog:
        return GoalLog(
            goal_id=row["goal_id"],
            day=parse_day(row["day"]),
            status=row["status"],
            intensity=row["intensity"],
            note=row["note"],
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def _task(self, row: Row) -> DailyTask:
        return DailyTask(
            id=row["id"],
            title=row["title"],
            day=parse_day(row["day"]),
            status=row["status"],
            planned_time=row["planned_time"],
            carry_forward=bool(row["carry_forward"]),
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    def _reflection(self, row: Row) -> Reflection:
        return Reflection(
            day=parse_day(row["day"]),
            mood=row["mood"],
            energy=row["energy"],
            note=row["note"],
            short_reflection=row["short_reflection"],
            is_vacation=bool(row["is_vacation"]),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )


def normalize_time(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if ":" not in value:
        return ""
    hour_raw, minute_raw = value.split(":", 1)
    try:
        hour = int(hour_raw)
        minute = int(minute_raw)
    except ValueError:
        return ""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"
