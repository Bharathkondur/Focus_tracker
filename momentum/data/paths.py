from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BASE_DIR = app_dir()
DB_PATH = BASE_DIR / "momentum.sqlite3"
APP_ICON_PATH = BASE_DIR / "Icon.png"
APP_ICON_ICO_PATH = BASE_DIR / "app_icon.ico"
LEGACY_DAILY_JSON = BASE_DIR / "daily_focus.json"
LEGACY_FOCUS_JSON = BASE_DIR / "focus_tracker_data.json"


def ensure_local_cwd() -> None:
    os.chdir(BASE_DIR)
