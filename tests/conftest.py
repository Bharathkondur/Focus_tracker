from __future__ import annotations

from pathlib import Path

import pytest

from momentum.data.database import Database
from momentum.data.repository import Repository


@pytest.fixture()
def temp_database(tmp_path: Path):
    database = Database(tmp_path / "momentum.sqlite3")
    try:
        yield database
    finally:
        database.close()


@pytest.fixture()
def temp_repo(temp_database: Database) -> Repository:
    return Repository(temp_database.conn)
