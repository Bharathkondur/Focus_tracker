# Momentum

A local-first desktop app for consistency, daily planning, and long-term habits. It is intentionally calm: dark graphite surfaces, soft emerald feedback, contribution-style heatmaps, and fast daily keyboard-friendly workflows.

## Stack

- Python
- PySide6
- SQLite
- Custom Qt widgets
- QSS dark theme

## Structure

```text
momentum/
  core/       domain models, date helpers, analytics
  data/       SQLite schema, repository, legacy JSON migration
  state/      Qt signal-based app store
  ui/         main window, sidebar, screens, widgets, QSS theme
```

## Features

- Separate recurring goals from temporary daily tasks with optional planned times.
- Per-goal 21-day consistency heatmaps.
- Sidebar yearly heatmap with day selection and vacation-day context menu.
- Right-click menus for goals, tasks, and heatmap cells.
- Reflection card with mood, energy, short reflection, and notes.
- Dashboard insights for weekly consistency, strongest and weakest habits, best weekday, and monthly trend.
- Local SQLite storage in `momentum.sqlite3`.
- Legacy `daily_focus.json` data is migrated on first run if the SQLite database is empty.

## Run From Source

```bash
python -m pip install -r requirements.txt
python focus_tracker.py
```

## Build The Exe

```bash
Build_Exe.bat
```

The app remains local-only. There is no account system, sync, or network dependency at runtime.
