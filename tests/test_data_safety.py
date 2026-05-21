from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from momentum.data.database import Database
from momentum.data.safety import create_backup, create_support_bundle, export_sql


class DataSafetyTests(unittest.TestCase):
    def test_backup_sql_export_and_support_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = Database(root / "momentum.sqlite3")
            try:
                database.conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('theme', 'dark')"
                )
                database.conn.commit()

                backup = create_backup(database.conn, root / "backups")
                sql = export_sql(database.conn, root / "exports")
                bundle = create_support_bundle(database.conn, root / "exports")
            finally:
                database.close()

            self.assertTrue(backup.exists())
            self.assertTrue(sql.exists())
            self.assertTrue(bundle.exists())
            with ZipFile(bundle) as archive:
                names = set(archive.namelist())
            self.assertIn("manifest.txt", names)
            self.assertTrue(any(name.startswith("database/") for name in names))


if __name__ == "__main__":
    unittest.main()
