from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from momentum.data.database import SCHEMA_VERSION, Database


class DatabaseSafetyTests(unittest.TestCase):
    def test_schema_version_backup_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = Database(root / "momentum.sqlite3")
            try:
                self.assertEqual(database.schema_version(), SCHEMA_VERSION)
                database.conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('theme', 'dark')"
                )
                database.conn.commit()

                backup = database.backup(root / "backups")
                export = database.export_sql(root / "exports")
            finally:
                database.close()

            self.assertTrue(backup.exists())
            self.assertTrue(export.exists())
            self.assertIn("CREATE TABLE", export.read_text(encoding="utf-8"))

            restored = root / "restored.sqlite3"
            Database.restore_backup(backup, restored)
            conn = sqlite3.connect(restored)
            try:
                value = conn.execute(
                    "SELECT value FROM settings WHERE key = 'theme'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(value, "dark")


if __name__ == "__main__":
    unittest.main()
