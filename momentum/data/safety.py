from __future__ import annotations

from datetime import datetime
from pathlib import Path
import platform
import sqlite3
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from momentum.core.logging import LOG_FILE
from momentum.data.database import SCHEMA_VERSION
from momentum.data.paths import BASE_DIR, DB_PATH


def create_backup(conn: sqlite3.Connection, backup_dir: Path | None = None) -> Path:
    target_dir = backup_dir or BASE_DIR / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"momentum-{_stamp()}.sqlite3"
    target_conn = sqlite3.connect(target)
    try:
        conn.backup(target_conn)
    finally:
        target_conn.close()
    return target


def export_sql(conn: sqlite3.Connection, export_dir: Path | None = None) -> Path:
    target_dir = export_dir or BASE_DIR / "exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"momentum-{_stamp()}.sql"
    target.write_text("\n".join(conn.iterdump()), encoding="utf-8")
    return target


def create_support_bundle(conn: sqlite3.Connection, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or BASE_DIR / "exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    bundle = target_dir / f"momentum-support-{_stamp()}.zip"
    sql_export = export_sql(conn, target_dir)
    manifest = _manifest()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.txt", manifest)
        archive.write(sql_export, f"database/{sql_export.name}")
        if LOG_FILE.exists():
            archive.write(LOG_FILE, f"logs/{LOG_FILE.name}")
        if DB_PATH.exists():
            archive.write(DB_PATH, f"database/{DB_PATH.name}")
    return bundle


def _manifest() -> str:
    return "\n".join(
        [
            "Momentum Support Bundle",
            f"Created: {datetime.now().isoformat(timespec='seconds')}",
            f"Schema version: {SCHEMA_VERSION}",
            f"Python: {sys.version.split()[0]}",
            f"Platform: {platform.platform()}",
            f"App directory: {BASE_DIR}",
        ]
    )


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
