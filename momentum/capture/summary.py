from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from momentum.core.analytics import best_weekday
from momentum.core.dates import date_key, parse_day, today
from momentum.data.repository import ARCHIVED, DONE, OPEN, SKIPPED, Repository


@dataclass(slots=True)
class SummaryMetric:
    label: str
    value: str
    detail: str = ""


@dataclass(slots=True)
class CaptureSummary:
    start: date
    end: date
    title: str
    metrics: list[SummaryMetric]
    bullets: list[str]
    focus: list[str]


def preset_range(name: str) -> tuple[date, date]:
    end = today()
    if name == "7d":
        return end - timedelta(days=6), end
    if name == "30d":
        return end - timedelta(days=29), end
    if name == "1y":
        return end - timedelta(days=364), end
    return end - timedelta(days=6), end


def build_summary(repo: Repository, start: date, end: date) -> CaptureSummary:
    if start > end:
        start, end = end, start
    scores = repo.day_scores(start, end)
    capture_rows = repo.conn.execute(
        """
        SELECT kind, clean_text, day, confidence, source, created_at
        FROM capture_events
        WHERE day BETWEEN ? AND ?
        ORDER BY day DESC, id DESC
        """,
        (date_key(start), date_key(end)),
    ).fetchall()
    task_rows = repo.conn.execute(
        """
        SELECT status, day FROM daily_tasks
        WHERE day BETWEEN ? AND ? AND status != ?
        """,
        (date_key(start), date_key(end), ARCHIVED),
    ).fetchall()
    reflection_rows = repo.conn.execute(
        """
        SELECT day, mood, energy, note, short_reflection
        FROM reflections
        WHERE day BETWEEN ? AND ?
        ORDER BY day DESC
        """,
        (date_key(start), date_key(end)),
    ).fetchall()

    trackable = sum(score.total - score.skipped for score in scores if not score.vacation)
    completed = sum(score.completed for score in scores if not score.vacation)
    consistency = round((completed / trackable) * 100) if trackable else 0
    active_days = sum(1 for score in scores if score.total > 0 or score.completed > 0)
    kind_counts = Counter(row["kind"] for row in capture_rows)
    task_status = Counter(row["status"] for row in task_rows)
    avg_energy = _average_energy(reflection_rows)
    top_kind = kind_counts.most_common(1)[0][0].title() if kind_counts else "-"

    metrics = [
        SummaryMetric("Consistency", f"{consistency}%", f"{completed}/{trackable} completed"),
        SummaryMetric("Captured", str(len(capture_rows)), f"{top_kind} was most common"),
        SummaryMetric("Tasks Done", str(task_status.get(DONE, 0)), f"{task_status.get(OPEN, 0)} still open"),
        SummaryMetric("Active Days", str(active_days), f"Best weekday: {best_weekday(scores)}"),
        SummaryMetric("Avg Energy", avg_energy, f"{len(reflection_rows)} reflections"),
        SummaryMetric("Skipped", str(task_status.get(SKIPPED, 0)), "intentionally deferred"),
    ]

    bullets = _activity_bullets(capture_rows, kind_counts, task_status, reflection_rows, consistency)
    focus = _focus_suggestions(kind_counts, task_status, consistency, reflection_rows)
    title = f"{date_key(start)} to {date_key(end)}"
    return CaptureSummary(start, end, title, metrics, bullets, focus)


def _activity_bullets(capture_rows, kind_counts: Counter, task_status: Counter, reflection_rows, consistency: int) -> list[str]:
    bullets = []
    if capture_rows:
        pieces = [f"{kind}: {count}" for kind, count in kind_counts.most_common()]
        bullets.append("Capture mix: " + ", ".join(pieces) + ".")
    else:
        bullets.append("No quick captures in this range yet.")
    if task_status:
        bullets.append(
            f"Tasks: {task_status.get(DONE, 0)} done, {task_status.get(OPEN, 0)} open, {task_status.get(SKIPPED, 0)} skipped."
        )
    else:
        bullets.append("No dated tasks were created in this range.")
    if reflection_rows:
        moods = Counter(row["mood"] for row in reflection_rows if row["mood"])
        mood = moods.most_common(1)[0][0] if moods else "not tagged"
        bullets.append(f"Reflections: {len(reflection_rows)} days captured; most common mood was {mood}.")
    else:
        bullets.append("No reflections were saved in this range.")
    bullets.append(f"Overall consistency landed at {consistency}%.")
    latest = [row["clean_text"] for row in capture_rows[:3] if row["clean_text"]]
    if latest:
        bullets.append("Latest captures: " + "; ".join(latest) + ".")
    return bullets


def _focus_suggestions(kind_counts: Counter, task_status: Counter, consistency: int, reflection_rows) -> list[str]:
    suggestions = []
    if task_status.get(OPEN, 0) > task_status.get(DONE, 0):
        suggestions.append("Close or reschedule open tasks before adding more work.")
    if kind_counts.get("goal", 0) == 0:
        suggestions.append("Add one recurring goal if this period needs more consistency.")
    if kind_counts.get("note", 0) < max(1, kind_counts.get("task", 0) // 4):
        suggestions.append("Capture a few notes about what worked, not only what needs doing.")
    if consistency < 60:
        suggestions.append("Choose one tiny daily action for the next 7 days.")
    elif consistency >= 85:
        suggestions.append("Keep the system stable; avoid overloading the next period.")
    if not reflection_rows:
        suggestions.append("Add a short reflection at the end of today.")
    return suggestions[:4] or ["Keep capturing normally; the system has enough signal for this period."]


def _average_energy(rows) -> str:
    values = [int(row["energy"]) for row in rows if row["energy"]]
    if not values:
        return "-"
    return f"{sum(values) / len(values):.1f}/5"
