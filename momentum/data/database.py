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

CREATE TABLE IF NOT EXISTS capture_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    planned_time TEXT NOT NULL DEFAULT '',
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capture_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    predicted_kind TEXT NOT NULL,
    corrected_kind TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capture_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    suggested_kind TEXT NOT NULL,
    day TEXT NOT NULL,
    planned_time TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS note_metadata (
    day TEXT PRIMARY KEY,
    pinned INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trash_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS engineering_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    day TEXT NOT NULL,
    project_id INTEGER,
    source_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS capture_project_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_event_id INTEGER,
    project_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capture_event_id) REFERENCES capture_events(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_goal_logs_day ON goal_logs(day);
CREATE INDEX IF NOT EXISTS idx_daily_tasks_day ON daily_tasks(day);
CREATE INDEX IF NOT EXISTS idx_capture_events_day ON capture_events(day);
CREATE INDEX IF NOT EXISTS idx_capture_events_kind ON capture_events(kind);
CREATE INDEX IF NOT EXISTS idx_capture_inbox_day ON capture_inbox(day);
CREATE INDEX IF NOT EXISTS idx_note_metadata_pinned ON note_metadata(pinned);
CREATE INDEX IF NOT EXISTS idx_trash_items_kind ON trash_items(kind);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_engineering_entries_day ON engineering_entries(day);
CREATE INDEX IF NOT EXISTS idx_engineering_entries_type ON engineering_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_engineering_entries_project ON engineering_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_capture_project_links_project ON capture_project_links(project_id);
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
        self._ensure_capture_search()
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

    def _ensure_capture_search(self) -> None:
        try:
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS capture_fts
                USING fts5(raw_text, clean_text, kind, context)
                """
            )
        except sqlite3.OperationalError:
            # Some Python builds omit FTS5. Capture memory still works with LIKE search.
            pass
