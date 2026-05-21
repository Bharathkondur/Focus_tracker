from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from momentum.core.dates import today
from momentum.data.repository import DONE, OPEN
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.utils import _clear_layout
from momentum.ui.widgets.cards import Card
class WorkspaceCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("InsightCard")
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Workspace")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        review = QHBoxLayout()
        self.review_label = QLabel("")
        self.review_label.setObjectName("Muted")
        self.review_label.setWordWrap(True)
        review.addWidget(self.review_label, 1)
        carry = QPushButton("Carry Tomorrow")
        carry.setObjectName("Ghost")
        _accessible(carry, "Carry open tasks to tomorrow")
        carry.clicked.connect(window.carry_open_tasks)
        review.addWidget(carry)
        skip = QPushButton("Skip Open")
        skip.setObjectName("Ghost")
        _accessible(skip, "Skip open tasks")
        skip.clicked.connect(window.skip_open_tasks)
        review.addWidget(skip)
        export = QPushButton("Export Week")
        export.setObjectName("Ghost")
        _accessible(export, "Export weekly summary")
        export.clicked.connect(window.export_week)
        review.addWidget(export)
        layout.addLayout(review)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search notes, tasks, goals...")
        _accessible(self.search, "Workspace search", "Search across notes, tasks, and goals")
        self.search.textChanged.connect(self.refresh_search)
        layout.addWidget(self.search)

        self.results = QVBoxLayout()
        self.results.setSpacing(8)
        layout.addLayout(self.results)

        self.inbox_title = QLabel("Inbox")
        self.inbox_title.setObjectName("Caption")
        layout.addWidget(self.inbox_title)
        self.inbox = QVBoxLayout()
        self.inbox.setSpacing(8)
        layout.addLayout(self.inbox)

    def refresh(self) -> None:
        tasks = self.window.repo.tasks_for_day(today())
        done = sum(1 for task in tasks if task.status == DONE)
        open_count = sum(1 for task in tasks if task.status == OPEN)
        note = self.window.repo.reflection(today()).note
        self.review_label.setText(
            f"Today: {done} done, {open_count} open, {'note captured' if note else 'no note yet'}."
        )
        self.refresh_search()
        self.refresh_inbox()

    def refresh_search(self) -> None:
        _clear_layout(self.results)
        query = self.search.text().strip()
        if not query:
            return
        for kind, text, detail in self.window.search_everything(query):
            self.results.addWidget(ResultRow(kind, text, detail))

    def refresh_inbox(self) -> None:
        _clear_layout(self.inbox)
        rows = self.window.memory.inbox_items(6)
        self.inbox_title.setVisible(bool(rows))
        if not rows:
            return
        for row in rows:
            self.inbox.addWidget(InboxRow(self.window, row))

class ResultRow(QFrame):
    def __init__(self, kind: str, text: str, detail: str):
        super().__init__()
        self.setObjectName("TimelineRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        chip = QLabel(kind)
        chip.setObjectName("Chip")
        chip.setFixedWidth(64)
        body = QVBoxLayout()
        title = QLabel(text)
        title.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        body.addWidget(title)
        body.addWidget(meta)
        layout.addWidget(chip)
        layout.addLayout(body, 1)

class InboxRow(QFrame):
    def __init__(self, window: CaptureWindow, row):
        super().__init__()
        self.setObjectName("TimelineRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        body = QVBoxLayout()
        title = QLabel(row["clean_text"])
        title.setWordWrap(True)
        meta = QLabel(f"Suggested {row['suggested_kind']} - {float(row['confidence']):.0%}")
        meta.setObjectName("Caption")
        body.addWidget(title)
        body.addWidget(meta)
        layout.addLayout(body, 1)
        for kind in ("task", "goal", "note"):
            button = QPushButton(kind.title())
            button.setObjectName("Ghost")
            _accessible(button, f"Save inbox item as {kind}")
            button.clicked.connect(lambda _checked=False, value=kind, row_id=row["id"]: window.accept_inbox_item(row_id, value))
            layout.addWidget(button)
