# Momentum

Momentum is a local-first Windows desktop app for daily planning, recurring habits, and quiet consistency tracking. It keeps the original Focus Tracker launchers, but the current app lives in the `momentum` package and uses a PySide6 interface with SQLite storage.

The app has no account system, sync, telemetry, or runtime network dependency. Your data stays in the app folder on this machine.

## Screenshots

![Momentum goals dashboard](screenshots/momentum-goals.png)

![Momentum reflection and insights](screenshots/momentum-insights.png)

## Features

- Recurring goals for habits you want to track over time.
- Daily tasks for one-off work, with optional `HH:MM` planned times.
- Carry-forward support for unfinished tasks.
- Goal and task notes through right-click menus.
- Mark goals or tasks as done, skipped, or archived.
- Per-goal 21-day consistency maps.
- Sidebar yearly consistency heatmap with day selection.
- Vacation-day marking from the heatmap context menu.
- Daily reflection with mood, energy, short reflection, and longer notes.
- Insight cards for weekly consistency, strongest habit, weakest habit, best weekday, and monthly trend.
- Local SQLite database stored as `momentum.sqlite3`.
- One-time migration from `daily_focus.json` when the SQLite database is empty.

## Tech Stack

- Python
- PySide6
- SQLite
- Custom Qt widgets
- QSS dark theme
- PyInstaller for the standalone executable

## Project Structure

```text
momentum/
  core/       domain models, date helpers, analytics
  data/       SQLite schema, repository, paths, legacy migration
  state/      Qt signal-based application store
  ui/         main window, sidebar, views, widgets, theme

focus_tracker.py      source launcher
FocusTracker.pyw      windowed launcher
Build_Exe.bat         Windows executable builder
FocusTracker.exe      standalone Windows build
```

## Run The Standalone App

Download or open `FocusTracker.exe`, then double-click it.

Momentum creates and updates `momentum.sqlite3` next to the executable. Keep that file if you want to preserve your data when moving the app folder.

## Run From Source

```bash
python -m pip install -r requirements.txt
python focus_tracker.py
```

On Windows, you can also run the windowed launcher:

```bash
python FocusTracker.pyw
```

## Build The Exe

Run the build script from the repository folder:

```bash
Build_Exe.bat
```

The script installs the app dependencies and PyInstaller for the current user, builds a single-file `FocusTracker.exe`, and creates a desktop shortcut named `Focus Tracker`.

## Data And Privacy

Momentum stores all app data locally in `momentum.sqlite3`. Local data files and generated build artifacts are ignored by Git where appropriate:

- `momentum.sqlite3*`
- `daily_focus.json`
- `focus_tracker_data.json`
- `build/`
- `dist/`
- `__pycache__/`

If `daily_focus.json` exists and `momentum.sqlite3` has no goals yet, Momentum imports the legacy daily goals, checks, tasks, task checks, notes, and mood values on first run.

## Development Notes

Use `requirements.txt` for runtime dependencies. The main application entry point is `momentum.main:main`, and both `focus_tracker.py` and `FocusTracker.pyw` delegate to it.
