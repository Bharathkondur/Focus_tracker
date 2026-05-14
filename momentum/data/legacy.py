from __future__ import annotations

import json
from pathlib import Path

from momentum.core.dates import parse_day
from momentum.data.paths import LEGACY_DAILY_JSON
from momentum.data.repository import DONE, MISSED, Repository


def migrate_daily_json(repo: Repository, path: Path = LEGACY_DAILY_JSON) -> None:
    if not path.exists():
        return
    if repo.all_goals():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(raw, dict):
        return

    goal_ids: dict[str, int] = {}
    for key in sorted(raw.keys()):
        entry = raw.get(key) or {}
        try:
            day = parse_day(key)
        except ValueError:
            continue
        goals = entry.get("goals", []) if isinstance(entry, dict) else []
        checks = entry.get("checks", []) if isinstance(entry, dict) else []
        tasks = entry.get("tasks", []) if isinstance(entry, dict) else []
        task_checks = entry.get("task_checks", []) if isinstance(entry, dict) else []
        for index, title in enumerate(goals):
            title = str(title).strip()
            if not title:
                continue
            if title not in goal_ids:
                goal_ids[title] = repo.add_goal(title, created_on=day).id
            repo.set_goal_status(
                goal_ids[title],
                day,
                DONE if index < len(checks) and checks[index] else MISSED,
            )
        for index, title in enumerate(tasks):
            title = str(title).strip()
            if not title:
                continue
            task = repo.add_task(title, day)
            if index < len(task_checks) and task_checks[index]:
                repo.set_task_status(task.id, DONE)
        reflection = repo.reflection(day)
        reflection.note = str(entry.get("notes", "") or "")
        reflection.mood = str(entry.get("mood", "") or "")
        repo.save_reflection(reflection)
