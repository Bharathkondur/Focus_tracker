from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from momentum.core.models import DayScore, Goal, GoalLog


DONE = "done"
SKIPPED = "skipped"
MISSED = "missed"


def weekly_consistency(scores: list[DayScore]) -> int:
    trackable = sum(score.total - score.skipped for score in scores if not score.vacation)
    completed = sum(score.completed for score in scores if not score.vacation)
    return round((completed / trackable) * 100) if trackable else 0


def best_weekday(scores: list[DayScore]) -> str:
    buckets: dict[int, list[int]] = defaultdict(list)
    for score in scores:
        if score.vacation or score.total == 0:
            continue
        buckets[score.day.weekday()].append(score.percent)
    if not buckets:
        return "-"
    weekday = max(buckets, key=lambda idx: sum(buckets[idx]) / len(buckets[idx]))
    return calendar.day_name[weekday]


def goal_streak(goal_id: int, logs: dict[tuple[int, date], GoalLog], start: date) -> int:
    streak = 0
    day = start
    while True:
        log = logs.get((goal_id, day))
        if not log or log.status != DONE:
            return streak
        streak += 1
        day -= timedelta(days=1)


def strongest_and_weakest(goals: list[Goal], logs: list[GoalLog]) -> tuple[str, str]:
    if not goals:
        return "-", "-"
    totals = {goal.id: [0, 0] for goal in goals}
    for log in logs:
        if log.goal_id not in totals or log.status == SKIPPED:
            continue
        totals[log.goal_id][1] += 1
        if log.status == DONE:
            totals[log.goal_id][0] += 1
    scored = []
    title_by_id = {goal.id: goal.title for goal in goals}
    for goal_id, (done, total) in totals.items():
        scored.append((done / total if total else 0, title_by_id[goal_id]))
    scored.sort()
    return scored[-1][1], scored[0][1]


def monthly_trend(scores: list[DayScore], month: date) -> int:
    current = [score.percent for score in scores if score.day.year == month.year and score.day.month == month.month]
    prev_year = month.year if month.month > 1 else month.year - 1
    prev_month = month.month - 1 if month.month > 1 else 12
    previous = [score.percent for score in scores if score.day.year == prev_year and score.day.month == prev_month]
    if not current:
        return 0
    return round(sum(current) / len(current) - (sum(previous) / len(previous) if previous else 0))
