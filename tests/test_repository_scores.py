from __future__ import annotations

from datetime import date, timedelta
import tempfile
import unittest
from pathlib import Path

from momentum.data.database import Database
from momentum.data.repository import DONE, Repository


class RepositoryScoreTests(unittest.TestCase):
    def test_day_scores_batches_task_query_for_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database = Database(Path(tmp) / "momentum.sqlite3")
            try:
                repo = Repository(database.conn)
                start = date(2026, 5, 1)
                for offset in range(10):
                    task = repo.add_task(f"task {offset}", start + timedelta(days=offset))
                    if offset % 2 == 0:
                        repo.set_task_status(task.id, DONE)

                statements: list[str] = []
                database.conn.set_trace_callback(statements.append)
                scores = repo.day_scores(start, start + timedelta(days=61))
                database.conn.set_trace_callback(None)
            finally:
                database.close()

        task_selects = [
            statement for statement in statements
            if "FROM daily_tasks" in statement and "BETWEEN" in statement
        ]
        self.assertEqual(len(scores), 62)
        self.assertEqual(len(task_selects), 1)
        self.assertEqual(sum(score.total for score in scores), 10)


if __name__ == "__main__":
    unittest.main()
