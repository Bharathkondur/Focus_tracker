from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from momentum.data.paths import BASE_DIR


LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "momentum.log"


def configure_logging() -> None:
    """Configure a small rotating local log for support/debugging."""
    if logging.getLogger().handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
