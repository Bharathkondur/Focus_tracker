from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from momentum.data.database import Database
from momentum.data.repository import Repository
from momentum.state.store import AppStore
from momentum.ui.capture_window import CaptureWindow


class CaptureUiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_capture_window_has_accessible_keyboard_entry_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "momentum.capture.local_model.LocalIntentModel.warmup_async",
            lambda self: None,
        ):
            database = Database(Path(tmp) / "momentum.sqlite3")
            try:
                window = CaptureWindow(AppStore(Repository(database.conn)))
                try:
                    window.show()
                    QApplication.processEvents()
                    self.assertEqual(window.accessibleName(), "Momentum Capture")
                    self.assertEqual(window.capture.input.accessibleName(), "Quick capture input")
                    self.assertEqual(window.library.search.accessibleName(), "Search library")
                    self.assertEqual(window.notebook.editor.accessibleName(), "Notebook editor")

                    shortcuts = {shortcut.key().toString() for shortcut in window.findChildren(QShortcut)}
                    self.assertIn("Ctrl+L", shortcuts)
                    self.assertIn("Ctrl+F", shortcuts)
                    self.assertIn("Ctrl+K", shortcuts)

                    window.focus_search()
                    QApplication.processEvents()
                    self.assertIs(QApplication.focusWidget(), window.library.search)
                finally:
                    window.close()
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
