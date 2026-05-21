from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from momentum.capture.summary import build_summary, preset_range
from momentum.core.dates import date_key, today
from momentum.data.repository import DONE, OPEN
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.utils import _clear_layout, _from_qdate, _to_qdate
from momentum.ui.capture.summary_card import SummaryCard
from momentum.ui.capture.workspace_card import InboxRow, ResultRow, WorkspaceCard
from momentum.ui.widgets.cards import Card


class EngineeringCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("InsightCard")
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Engineering Log")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        standup = QPushButton("Standup")
        standup.setObjectName("Ghost")
        standup.clicked.connect(window.export_standup)
        header.addWidget(standup)
        report = QPushButton("Report")
        report.setObjectName("Ghost")
        report.clicked.connect(window.export_engineering_report)
        header.addWidget(report)
        layout.addLayout(header)

        self.items = QVBoxLayout()
        self.items.setSpacing(8)
        layout.addLayout(self.items)

    def refresh(self) -> None:
        _clear_layout(self.items)
        rows = self.window.repo.conn.execute(
            """
            SELECT e.*, p.name AS project_name
            FROM engineering_entries e
            LEFT JOIN projects p ON p.id = e.project_id
            WHERE e.day >= ?
            ORDER BY e.day DESC, e.id DESC
            LIMIT 8
            """,
            (date_key(today() - timedelta(days=7)),),
        ).fetchall()
        if not rows:
            self._add("No engineering entries yet.", "Try: decision: use sqlite for local storage")
            return
        for row in rows:
            detail = f"{row['entry_type']} - {row['day']}"
            if row["project_name"]:
                detail = f"{detail} - {row['project_name']}"
            self._add(row["title"], detail)

    def _add(self, title: str, detail: str) -> None:
        row = QFrame()
        row.setObjectName("TimelineRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel(title)
        label.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        layout.addWidget(label)
        layout.addWidget(meta)
        self.items.addWidget(row)

class CaptureCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("ReflectionCard")
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        row = QHBoxLayout()
        title = QLabel("What do you want to remember?")
        title.setObjectName("SectionTitle")
        row.addWidget(title)
        row.addStretch()
        self.buttons = QButtonGroup(self)
        self.buttons.setExclusive(True)
        self.kind_buttons = {}
        for kind in ("auto", "task", "goal", "note"):
            button = QPushButton(kind.title())
            _accessible(button, f"Capture mode {kind}")
            button.setCheckable(True)
            button.setObjectName("Primary" if kind == "auto" else "Ghost")
            if kind == "auto":
                button.setChecked(True)
            self.buttons.addButton(button)
            self.kind_buttons[kind] = button
            button.clicked.connect(lambda _checked=False, value=kind: window.set_kind(value))
            row.addWidget(button)
        layout.addLayout(row)

        self.input = ComposerEdit()
        self.input.setPlaceholderText("Write a task, goal, or note...")
        _accessible(self.input, "Quick capture input", "Write a task, goal, or note. Enter saves and Shift Enter adds a line.")
        self.input.submitted.connect(window.submit)
        self.input.textChanged.connect(window.update_preview)
        layout.addWidget(self.input)

        hint = QLabel("Enter saves. Shift+Enter adds a new line.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def set_active_kind(self, kind: str) -> None:
        for name, button in self.kind_buttons.items():
            is_active = name == kind
            button.setChecked(is_active)
            button.setObjectName("Primary" if is_active else "Ghost")
            button.style().unpolish(button)
            button.style().polish(button)

    def set_prediction(self, kind: str, detail: str) -> None:
        if self.window.forced_kind != "auto":
            return
        for name, button in self.kind_buttons.items():
            is_active = name == (kind or "auto")
            button.setChecked(is_active)
            button.setObjectName("Primary" if is_active else "Ghost")
            button.style().unpolish(button)
            button.style().polish(button)


class SectionList(Card):
    def __init__(self, title: str, compact: bool = False):
        super().__init__("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14 if compact else 18, 12 if compact else 16, 14 if compact else 18, 14 if compact else 18)
        layout.setSpacing(8 if compact else 12)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        self.list = QListWidget()
        _accessible(self.list, f"{title} list")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setMinimumHeight(120 if compact else 180)
        layout.addWidget(self.list, 1)

    def add(self, title: str, detail: str) -> None:
        self.list.addItem(f"{title}\n{detail}")

    def clear(self) -> None:
        self.list.clear()


class SaveActionBar(QFrame):
    def __init__(self, window: CaptureWindow):
        super().__init__()
        self.window = window
        self.setObjectName("ActionBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        self.label = QLabel("")
        self.label.setObjectName("Muted")
        layout.addWidget(self.label, 1)
        undo = QPushButton("Undo")
        undo.setObjectName("Ghost")
        undo.clicked.connect(window.undo_last_save)
        layout.addWidget(undo)
        for kind in ("task", "goal", "note"):
            button = QPushButton(f"Change to {kind.title()}")
            button.setObjectName("Ghost")
            button.clicked.connect(lambda _checked=False, value=kind: window.change_last_save(value))
            layout.addWidget(button)

    def show_saved(self, kind: str, text: str) -> None:
        self.label.setText(f"Saved as {kind.title()}: {text[:90]}")
        self.setVisible(True)


class TimelineCard(Card):
    def __init__(self, title: str):
        super().__init__("InsightCard")
        self.empty = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        self.items = QVBoxLayout()
        self.items.setSpacing(8)
        layout.addLayout(self.items)

    def add(self, kind: str, text: str, detail: str) -> None:
        self.empty = False
        row = QFrame()
        row.setObjectName("TimelineRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        chip = QLabel(kind)
        chip.setObjectName("Chip")
        chip.setFixedWidth(64)
        body = QVBoxLayout()
        title = QLabel(text)
        title.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        body.addWidget(title)
        if detail:
            body.addWidget(meta)
        layout.addWidget(chip)
        layout.addLayout(body, 1)
        self.items.addWidget(row)

    def clear(self) -> None:
        self.empty = True
        while self.items.count():
            item = self.items.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


class ComposerEdit(QTextEdit):
    submitted = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Composer")
        _accessible(self, "Composer")
        self.setAcceptRichText(False)
        self.setMinimumHeight(124)
        self.setMaximumHeight(180)

    def text(self) -> str:
        return self.toPlainText()

    def clear(self) -> None:
        super().clear()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)
