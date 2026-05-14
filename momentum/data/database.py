from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    cadence TEXT NOT NULL DEFAULT 'daily',
    color TEXT NOT NULL DEFAULT '#34D399',
    created_on TEXT NOT NULL,
    archived_on TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goal_logs (
    goal_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'missed',
    intensity INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (goal_id, day),
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    day TEXT NOT NULL,
    planned_time TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    carry_forward INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS reflections (
    day TEXT PRIMARY KEY,
    mood TEXT NOT NULL DEFAULT '',
    energy INTEGER NOT NULL DEFAULT 3,
    note TEXT NOT NULL DEFAULT '',
    short_reflection TEXT NOT NULL DEFAULT '',
    is_vacation INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goal_logs_day ON goal_logs(day);
CREATE INDEX IF NOT EXISTS idx_daily_tasks_day ON daily_tasks(day);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self.migrate()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def migrate(self) -> None:
        self._conn.executescript(SCHEMA)
        self._ensure_column("daily_tasks", "planned_time", "TEXT NOT NULL DEFAULT ''")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
