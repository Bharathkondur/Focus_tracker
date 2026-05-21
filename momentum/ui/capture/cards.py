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


class SummaryCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("InsightCard")
        self.window = window
        self.current_preset = "7d"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Momentum Summary")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.buttons = {}
        for label, preset in (("7 Days", "7d"), ("1 Month", "30d"), ("1 Year", "1y")):
            button = QPushButton(label)
            button.setObjectName("Primary" if preset == self.current_preset else "Ghost")
            _accessible(button, f"Show {label} summary")
            button.clicked.connect(lambda _checked=False, value=preset: self.set_preset(value))
            self.buttons[preset] = button
            header.addWidget(button)
        layout.addLayout(header)

        custom = QHBoxLayout()
        custom.addWidget(QLabel("From"))
        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        _accessible(self.start_edit, "Summary start date")
        custom.addWidget(self.start_edit)
        custom.addWidget(QLabel("To"))
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        _accessible(self.end_edit, "Summary end date")
        custom.addWidget(self.end_edit)
        apply_button = QPushButton("Apply")
        _accessible(apply_button, "Apply custom summary date range")
        apply_button.clicked.connect(self.apply_custom)
        custom.addWidget(apply_button)
        layout.addLayout(custom)

        self.range_label = QLabel("")
        self.range_label.setObjectName("Caption")
        layout.addWidget(self.range_label)

        self.metrics = QGridLayout()
        self.metrics.setHorizontalSpacing(10)
        self.metrics.setVerticalSpacing(10)
        self.metric_cards: list[MetricTile] = []
        for index in range(6):
            tile = MetricTile()
            self.metric_cards.append(tile)
            self.metrics.addWidget(tile, index // 3, index % 3)
        layout.addLayout(self.metrics)

        lists = QHBoxLayout()
        lists.setSpacing(12)
        self.bullets = SimpleTextPanel("What Happened")
        self.focus = SimpleTextPanel("Suggested Focus")
        lists.addWidget(self.bullets, 1)
        lists.addWidget(self.focus, 1)
        layout.addLayout(lists)

        self.set_preset("7d")

    def set_preset(self, preset: str) -> None:
        self.current_preset = preset
        for key, button in self.buttons.items():
            button.setObjectName("Primary" if key == preset else "Ghost")
            button.style().unpolish(button)
            button.style().polish(button)
        start, end = preset_range(preset)
        self.start_edit.setDate(_to_qdate(start))
        self.end_edit.setDate(_to_qdate(end))
        self.refresh()

    def apply_custom(self) -> None:
        self.current_preset = "custom"
        for button in self.buttons.values():
            button.setObjectName("Ghost")
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh()

    def refresh(self) -> None:
        start = _from_qdate(self.start_edit.date())
        end = _from_qdate(self.end_edit.date())
        summary = build_summary(self.window.repo, start, end)
        self.range_label.setText(summary.title)
        for tile, metric in zip(self.metric_cards, summary.metrics):
            tile.set_metric(metric.label, metric.value, metric.detail)
        self.bullets.clear()
        for item in summary.bullets:
            self.bullets.add(item)
        self.focus.clear()
        for item in summary.focus:
            self.focus.add(item)


class MetricTile(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.label = QLabel("")
        self.label.setObjectName("Muted")
        self.value = QLabel("")
        self.value.setObjectName("Metric")
        self.detail = QLabel("")
        self.detail.setObjectName("Caption")
        self.detail.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_metric(self, label: str, value: str, detail: str) -> None:
        self.label.setText(label)
        self.value.setText(value)
        self.detail.setText(detail)


class SimpleTextPanel(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("Caption")
        layout.addWidget(label)
        self.items = QVBoxLayout()
        self.items.setSpacing(6)
        layout.addLayout(self.items)
        layout.addStretch()

    def add(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        self.items.addWidget(label)

    def clear(self) -> None:
        while self.items.count():
            item = self.items.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
