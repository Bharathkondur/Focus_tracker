from __future__ import annotations

from datetime import date, timedelta

from momentum.core.analytics import (
    best_weekday,
    goal_streak,
    monthly_trend,
    strongest_and_weakest,
    weekly_consistency,
)
from momentum.core.models import DayScore, Goal, GoalLog


def test_weekly_consistency_ignores_skipped_and_vacation_days() -> None:
    scores = [
        DayScore(date(2026, 5, 18), total=3, completed=2, skipped=1),
        DayScore(date(2026, 5, 19), total=4, completed=4, vacation=True),
        DayScore(date(2026, 5, 20), total=2, completed=1),
    ]

    assert weekly_consistency(scores) == 75


def test_best_weekday_ignores_empty_and_vacation_scores() -> None:
    scores = [
        DayScore(date(2026, 5, 18), total=2, completed=1),
        DayScore(date(2026, 5, 19), total=2, completed=2),
        DayScore(date(2026, 5, 26), total=2, completed=0, vacation=True),
        DayScore(date(2026, 5, 27), total=0, completed=0),
    ]

    assert best_weekday(scores) == "Tuesday"
    assert best_weekday([]) == "-"


def test_goal_streak_walks_backward_until_first_miss() -> None:
    start = date(2026, 5, 21)
    logs = {
        (7, start): GoalLog(7, start, "done"),
        (7, start - timedelta(days=1)): GoalLog(7, start - timedelta(days=1), "done"),
        (7, start - timedelta(days=2)): GoalLog(7, start - timedelta(days=2), "missed"),
    }

    assert goal_streak(7, logs, start) == 2


def test_strongest_and_weakest_ignore_skipped_logs() -> None:
    goals = [
        Goal(1, "exercise", "daily", "#fff", date(2026, 5, 1)),
        Goal(2, "reading", "daily", "#fff", date(2026, 5, 1)),
    ]
    logs = [
        GoalLog(1, date(2026, 5, 1), "done"),
        GoalLog(1, date(2026, 5, 2), "skipped"),
        GoalLog(2, date(2026, 5, 1), "missed"),
        GoalLog(2, date(2026, 5, 2), "done"),
    ]

    assert strongest_and_weakest(goals, logs) == ("exercise", "reading")
    assert strongest_and_weakest([], logs) == ("-", "-")


def test_monthly_trend_compares_current_month_to_previous_month() -> None:
    scores = [
        DayScore(date(2026, 4, 1), total=2, completed=1),
        DayScore(date(2026, 4, 2), total=2, completed=1),
        DayScore(date(2026, 5, 1), total=2, completed=2),
        DayScore(date(2026, 5, 2), total=2, completed=1),
    ]

    assert monthly_trend(scores, date(2026, 5, 1)) == 25
    assert monthly_trend([], date(2026, 5, 1)) == 0
