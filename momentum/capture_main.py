from __future__ import annotations

import sys
from datetime import timedelta

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from momentum.core.dates import date_key, today
from momentum.data.database import Database
from momentum.data.legacy import migrate_daily_json
from momentum.data.paths import APP_ICON_PATH, DB_PATH, ensure_local_cwd
from momentum.data.repository import Repository
from momentum.state.store import AppStore
from momentum.ui.capture_window import CaptureWindow
from momentum.ui.theme import app_font, load_stylesheet


def carry_tasks_once(repo: Repository) -> None:
    key = f"capture_carry_forward_done:{date_key(today())}"
    if repo.setting(key):
        return
    repo.carry_unfinished_tasks(today() - timedelta(days=1), today())
    repo.set_setting(key, "1")


def main() -> int:
    ensure_local_cwd()
    app = QApplication(sys.argv)
    app.setApplicationName("Momentum Capture")
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setFont(app_font())

    database = Database(DB_PATH)
    repo = Repository(database.conn)
    app.setStyleSheet(load_stylesheet(repo.setting("theme", "dark")))
    migrate_daily_json(repo)
    carry_tasks_once(repo)
    store = AppStore(repo)

    window = CaptureWindow(store)
    window.show()
    result = app.exec()
    database.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
