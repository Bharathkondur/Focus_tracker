from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import shutil
import logging


logger = logging.getLogger(__name__)
SCHEMA_VERSION = 2


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

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        self._backup_on_startup_if_stale()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def migrate(self) -> None:
        self._conn.executescript(SCHEMA)
        self._ensure_column("daily_tasks", "planned_time", "TEXT NOT NULL DEFAULT ''")
        self._ensure_capture_search()
        self._set_schema_version(SCHEMA_VERSION)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        return int(row["version"]) if row else 0

    def backup(self, backup_dir: Path | None = None) -> Path:
        target_dir = backup_dir or self.path.parent / "backups"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = target_dir / f"{self.path.stem}-{stamp}.sqlite3"
        target_conn = sqlite3.connect(target)
        try:
            self._conn.backup(target_conn)
        finally:
            target_conn.close()
        return target

    def export_sql(self, export_dir: Path | None = None) -> Path:
        target_dir = export_dir or self.path.parent / "exports"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = target_dir / f"{self.path.stem}-{stamp}.sql"
        target.write_text("\n".join(self._conn.iterdump()), encoding="utf-8")
        return target

    @staticmethod
    def restore_backup(source: Path, destination: Path) -> None:
        if not source.exists():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _set_schema_version(self, version: int) -> None:
        self._conn.execute(
            """
            INSERT INTO schema_version (id, version, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                version = excluded.version,
                updated_at = CURRENT_TIMESTAMP
            """,
            (version,),
        )

    def _backup_on_startup_if_stale(self) -> None:
        key = "last_startup_backup_at"
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        now = datetime.now()
        last_backup = None
        if row:
            try:
                last_backup = datetime.fromisoformat(row["value"])
            except ValueError:
                logger.exception("Invalid startup backup timestamp in settings")
        if last_backup is not None and now - last_backup < timedelta(hours=24):
            return
        self.backup()
        self._conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, now.isoformat(timespec="seconds")),
        )
        self._conn.commit()

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
            logger.exception("SQLite FTS5 is unavailable; capture memory will use LIKE search")
            pass
