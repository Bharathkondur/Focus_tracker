from __future__ import annotations

import json
from datetime import date, timedelta
from dataclasses import dataclass

from PySide6.QtCore import QDate, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QApplication,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from momentum.capture.files import append_capture, export_weekly_summary
from momentum.capture.intent import CaptureIntent
from momentum.capture.memory import CaptureMemory, CaptureRecord
from momentum.capture.router import ContextRouter, RoutedCapture
from momentum.capture.summary import build_summary, preset_range
from momentum.core.dates import date_key, parse_day, today
from momentum.data.paths import BASE_DIR
from momentum.data.repository import DONE, OPEN, SKIPPED
from momentum.data.repository import Repository
from momentum.state.store import AppStore
from momentum.ui.theme import load_stylesheet
from momentum.ui.widgets.cards import Card


@dataclass(slots=True)
class LastSave:
    raw: str
    clean_text: str
    kind: str
    day: object
    entity_type: str
    entity_id: int | None
    capture_event_id: int


class CaptureWindow(QMainWindow):
    def __init__(self, store: AppStore):
        super().__init__()
        self.store = store
        self.repo: Repository = store.repo
        self.memory = CaptureMemory(self.repo.conn)
        self.router = ContextRouter(self.memory)
        self.forced_kind = "auto"
        self.last_route: RoutedCapture | None = None
        self.last_save: LastSave | None = None
        self.focus_mode = False
        self.theme_mode = self.repo.setting("theme", "dark") or "dark"

        self.setWindowTitle("Momentum Capture")
        self.resize(1280, 820)
        self.setMinimumSize(1080, 720)

        root = QWidget()
        root.setObjectName("Root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.library = LibrarySidebar(self)
        shell.addWidget(self.library)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content = QWidget()
        content.setObjectName("ComposerPage")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(42, 46, 42, 34)
        content_layout.setSpacing(18)

        header = QVBoxLayout()
        header.setSpacing(8)
        day = QLabel(date_key(today()).upper())
        day.setObjectName("Caption")
        title = QLabel("Today")
        title.setObjectName("Hero")
        sub = QLabel("Capture quickly. Keep today's note open.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        header.addWidget(day)
        header.addWidget(title)
        header.addWidget(sub)
        content_layout.addLayout(header)

        self.capture = CaptureCard(self)
        content_layout.addWidget(self.capture)

        self.notebook = LibraryEditorCard(self)
        content_layout.addWidget(self.notebook)

        self.preview = QLabel("Ready.")
        self.preview.setObjectName("Caption")
        self.preview.setWordWrap(True)
        self.preview.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.preview)

        self.action_bar = SaveActionBar(self)
        self.action_bar.setVisible(False)
        content_layout.addWidget(self.action_bar)

        self.timeline = TimelineCard("Today")
        self.engineering = EngineeringCard(self)
        self.workspace = WorkspaceCard(self)
        self.summary = SummaryCard(self)
        content_layout.addStretch()

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        outer.addWidget(content, 0)
        outer.addStretch(1)
        layout.addLayout(outer)

        shell.addWidget(scroll, 1)
        self.setCentralWidget(root)

        store.data_changed.connect(self.refresh)
        store.day_changed.connect(self.refresh)
        self.apply_theme(self.theme_mode, persist=False)
        self.refresh()

        shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut.activated.connect(self.capture.input.setFocus)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self.set_kind("task"))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self.set_kind("goal"))
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(lambda: self.set_kind("note"))
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(lambda: self.set_kind("auto"))
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.undo_last_save)
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self.export_week)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.notebook.save_current)
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self.open_command_palette)

    def set_kind(self, kind: str) -> None:
        self.forced_kind = kind
        self.capture.set_active_kind(kind)
        self.update_preview()

    def update_preview(self) -> None:
        route = self._route()
        self.last_route = route
        if route is None:
            self.preview.setText("Ready.")
            self.capture.set_prediction("", "")
            return
        intent = route.intent
        self.capture.set_prediction(intent.kind, self._date_chip(intent))
        if route.needs_confirmation:
            self.preview.setText("Choose the right destination before saving.")
        else:
            self.preview.setText(self._date_chip(intent))

    def submit(self) -> None:
        raw_value = self.capture.input.text()
        auto_route = None
        if self.forced_kind != "auto":
            auto_route = self.router.route(raw_value, today(), "auto")
        route = self._route()
        if route is None:
            return
        intent = route.intent
        if route.needs_confirmation and self.forced_kind == "auto":
            self.memory.send_to_inbox(intent, route.confidence, route.source)
            self.capture.input.clear()
            self.preview.setText("Saved to inbox for review.")
            self.action_bar.setVisible(False)
            self.refresh()
            return
        path = append_capture(intent)
        entity_type, entity_id = self._save_to_app(intent)
        capture_event_id = self.memory.remember(
            CaptureRecord(
                intent=intent,
                confidence=route.confidence,
                source=route.source,
                entity_type=entity_type,
                entity_id=entity_id,
                context="; ".join(f"{item.kind}:{item.text}" for item in route.context[:5]),
            )
        )
        if auto_route is not None and auto_route.intent.kind != intent.kind:
            self.memory.remember_correction(
                intent.raw,
                intent.text,
                auto_route.intent.kind,
                intent.kind,
            )
        self.last_save = LastSave(
            raw=intent.raw,
            clean_text=intent.text,
            kind=intent.kind,
            day=intent.day,
            entity_type=entity_type,
            entity_id=entity_id,
            capture_event_id=capture_event_id,
        )
        project_id = _project_for_text(self.repo.conn, intent.text)
        if project_id is not None:
            _link_capture_project(self.repo.conn, capture_event_id, project_id, entity_type, entity_id)
        _record_engineering_entry(self.repo.conn, intent, project_id)
        self.capture.input.clear()
        self.preview.setText("Ready.")
        if intent.kind in {"note", "plan"} and self.notebook.current_kind == "note":
            if self.notebook.current_day == intent.day:
                self.notebook.load_note_day(intent.day)
        self.action_bar.show_saved(intent.kind, intent.text)
        self.refresh()

    def refresh(self) -> None:
        self.timeline.clear()
        selected = today()
        for goal in self.repo.active_goals():
            self.timeline.add("Goal", goal.title, "recurring")
        for task in self.repo.tasks_for_day(selected):
            suffix = f" at {task.planned_time}" if task.planned_time else ""
            self.timeline.add("Task", task.title, f"{task.status}{suffix}")
        reflection = self.repo.reflection(selected)
        if reflection.short_reflection:
            self.timeline.add("Note", reflection.short_reflection, "reflection")
        if reflection.note:
            self.timeline.add("Note", reflection.note[-140:], "today")
        if self.timeline.empty:
            self.timeline.add("Today", "Start with one thing you want to remember.", "")
        self.library.refresh()
        self.engineering.refresh()
        self.workspace.refresh()
        self.summary.refresh()

    def _route(self) -> RoutedCapture | None:
        return self.router.route(self.capture.input.text(), today(), self.forced_kind)

    def undo_last_save(self) -> None:
        if self.last_save is None:
            return
        saved = self.last_save
        self._remove_saved_entity(saved)
        self.memory.forget(saved.capture_event_id)
        if saved.entity_type == "reflection_note" and self.notebook.current_kind == "note":
            if self.notebook.current_day == saved.day:
                self.notebook.load_note_day(saved.day)
        self.last_save = None
        self.action_bar.setVisible(False)
        self.preview.setText("Undone.")
        self.store.data_changed.emit()
        self.refresh()

    def change_last_save(self, kind: str) -> None:
        if self.last_save is None:
            return
        raw = self.last_save.raw
        predicted = self.last_save.kind
        self.memory.remember_correction(raw, self.last_save.clean_text, predicted, kind)
        self.undo_last_save()
        self.capture.input.setPlainText(raw)
        self.forced_kind = kind
        self.capture.set_active_kind(kind)
        self.submit()
        self.forced_kind = "auto"
        self.capture.set_active_kind("auto")

    def carry_open_tasks(self) -> None:
        tomorrow = today() + timedelta(days=1)
        existing = {task.title.strip().lower() for task in self.repo.tasks_for_day(tomorrow)}
        moved = 0
        for task in self.repo.tasks_for_day(today()):
            key = task.title.strip().lower()
            if task.status != OPEN or key in existing:
                continue
            new_task = self.repo.add_task(task.title, tomorrow, task.carry_forward, task.planned_time)
            if task.note:
                self.repo.set_task_note(new_task.id, task.note)
            self.repo.set_task_status(task.id, SKIPPED)
            existing.add(key)
            moved += 1
        self.preview.setText(f"Carried {moved} open task{'s' if moved != 1 else ''} to tomorrow.")
        self.store.data_changed.emit()
        self.refresh()

    def skip_open_tasks(self) -> None:
        count = 0
        for task in self.repo.tasks_for_day(today()):
            if task.status == OPEN:
                self.repo.set_task_status(task.id, SKIPPED)
                count += 1
        self.preview.setText(f"Skipped {count} open task{'s' if count != 1 else ''}.")
        self.store.data_changed.emit()
        self.refresh()

    def export_week(self) -> None:
        path = export_weekly_summary(self.repo)
        self.preview.setText(f"Weekly summary exported: {path.name}")

    def export_engineering_report(self) -> None:
        path = _export_engineering_report(self.repo.conn)
        self.preview.setText(f"Engineering report exported: {path.name}")

    def export_standup(self) -> None:
        path = _export_standup(self.repo.conn, self.repo)
        self.preview.setText(f"Standup exported: {path.name}")

    def focus_search(self) -> None:
        self.library.search.setFocus()

    def open_note_day(self, day: date) -> None:
        self.notebook.load_note_day(day)
        self.preview.setText(f"Opened notes for {date_key(day)}.")

    def open_task(self, task_id: int) -> None:
        self.notebook.load_task(task_id)
        self.preview.setText("Opened task.")

    def open_goal(self, goal_id: int) -> None:
        self.notebook.load_goal(goal_id)
        self.preview.setText("Opened goal.")

    def open_project(self, project_id: int) -> None:
        self.notebook.load_project(project_id)
        self.preview.setText("Opened project.")

    def toggle_focus_mode(self) -> None:
        self.focus_mode = not self.focus_mode
        for widget in (self.capture, self.preview, self.timeline, self.engineering, self.workspace, self.summary):
            widget.setVisible(not self.focus_mode)
        self.action_bar.setVisible(False if self.focus_mode else self.last_save is not None)
        self.notebook.set_focus_mode(self.focus_mode)

    def open_command_palette(self) -> None:
        CommandPalette(self).exec()

    def toggle_theme(self) -> None:
        self.apply_theme("light" if self.theme_mode == "dark" else "dark")

    def apply_theme(self, theme: str, persist: bool = True) -> None:
        self.theme_mode = "light" if theme == "light" else "dark"
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(load_stylesheet(self.theme_mode))
        if persist:
            self.repo.set_setting("theme", self.theme_mode)
        if hasattr(self, "library"):
            self.library.update_theme_button()

    def search_everything(self, query: str) -> list[tuple[str, str, str]]:
        query = query.strip()
        if not query:
            return []
        like = f"%{query}%"
        results: list[tuple[str, str, str]] = []
        for row in self.repo.conn.execute(
            "SELECT title, created_on FROM goals WHERE title LIKE ? OR note LIKE ? ORDER BY id DESC LIMIT 8",
            (like, like),
        ).fetchall():
            results.append(("Goal", row["title"], row["created_on"]))
        for row in self.repo.conn.execute(
            "SELECT title, day, status FROM daily_tasks WHERE title LIKE ? OR note LIKE ? ORDER BY day DESC, id DESC LIMIT 8",
            (like, like),
        ).fetchall():
            results.append(("Task", row["title"], f"{row['day']} - {row['status']}"))
        for row in self.repo.conn.execute(
            """
            SELECT day, note, short_reflection FROM reflections
            WHERE note LIKE ? OR short_reflection LIKE ?
            ORDER BY day DESC LIMIT 8
            """,
            (like, like),
        ).fetchall():
            text = row["short_reflection"] or row["note"]
            results.append(("Note", text[:120], row["day"]))
        for row in self.repo.conn.execute(
            "SELECT clean_text, kind, day FROM capture_events WHERE clean_text LIKE ? ORDER BY id DESC LIMIT 8",
            (like,),
        ).fetchall():
            results.append((row["kind"].title(), row["clean_text"], row["day"]))
        return results[:20]

    def accept_inbox_item(self, inbox_id: int, kind: str) -> None:
        row = self.repo.conn.execute("SELECT * FROM capture_inbox WHERE id = ?", (inbox_id,)).fetchone()
        if row is None:
            return
        self.memory.remove_inbox_item(inbox_id)
        self.memory.remember_correction(row["raw_text"], row["clean_text"], row["suggested_kind"], kind)
        self.capture.input.setPlainText(f"{kind}: {row['raw_text']}")
        self.submit()

    def _remove_saved_entity(self, saved: LastSave) -> None:
        if saved.entity_type == "goal" and saved.entity_id is not None:
            self.repo.conn.execute("DELETE FROM goals WHERE id = ?", (saved.entity_id,))
            self.repo.conn.commit()
        elif saved.entity_type == "task" and saved.entity_id is not None:
            self.repo.conn.execute("DELETE FROM daily_tasks WHERE id = ?", (saved.entity_id,))
            self.repo.conn.commit()
        elif saved.entity_type == "reflection_note":
            reflection = self.repo.reflection(saved.day)
            reflection.note = _remove_appended_text(reflection.note, saved.clean_text)
            self.repo.save_reflection(reflection)

    def _date_chip(self, intent: CaptureIntent) -> str:
        when = "Today" if intent.day == today() else intent.day.strftime("%b %d")
        pieces = [intent.kind.title(), when]
        if intent.planned_time:
            pieces.append(intent.planned_time)
        return " - ".join(pieces)

    def _save_to_app(self, intent: CaptureIntent) -> tuple[str, int | None]:
        if intent.kind == "goal":
            goal = self.repo.add_goal(intent.text, created_on=intent.day)
            result = ("goal", goal.id)
        elif intent.kind == "task":
            task = self.repo.add_task(intent.text, intent.day, intent.carry_forward, intent.planned_time)
            result = ("task", task.id)
        elif intent.kind == "note":
            reflection = self.repo.reflection(intent.day)
            reflection.note = _append_text(reflection.note, intent.text)
            self.repo.save_reflection(reflection)
            result = ("reflection_note", None)
        elif intent.kind == "plan":
            reflection = self.repo.reflection(intent.day)
            reflection.note = _append_text(reflection.note, intent.text)
            self.repo.save_reflection(reflection)
            result = ("reflection_note", None)
        else:
            result = ("", None)
        self.store.data_changed.emit()
        return result


class LibrarySidebar(QFrame):
    def __init__(self, window: CaptureWindow):
        super().__init__()
        self.window = window
        self.mode = "note"
        self.setObjectName("Sidebar")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(12)

        brand = QLabel("Momentum")
        brand.setObjectName("Brand")
        layout.addWidget(brand)

        subtitle = QLabel("Notebook")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)

        theme_row = QHBoxLayout()
        theme_row.addStretch()
        self.theme_button = QPushButton("")
        self.theme_button.setObjectName("Ghost")
        self.theme_button.clicked.connect(window.toggle_theme)
        theme_row.addWidget(self.theme_button)
        layout.addLayout(theme_row)

        tabs = QGridLayout()
        tabs.setHorizontalSpacing(8)
        tabs.setVerticalSpacing(8)
        self.buttons: dict[str, QPushButton] = {}
        for index, (label, mode) in enumerate((("Notes", "note"), ("Tasks", "task"), ("Goals", "goal"), ("Projects", "project"), ("Reports", "reports"), ("Trash", "trash"))):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=mode: self.set_mode(value))
            self.buttons[mode] = button
            tabs.addWidget(button, index // 3, index % 3)
        layout.addLayout(tabs)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search library...")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.new_note = QPushButton("New Today Note")
        self.new_note.setObjectName("Primary")
        self.new_note.clicked.connect(lambda: self.window.open_note_day(today()))
        layout.addWidget(self.new_note)

        self.list = QListWidget()
        self.list.setObjectName("LibraryList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.setSpacing(4)
        self.list.itemClicked.connect(self.open_item)
        layout.addWidget(self.list, 1)

        hint = QLabel("Click a day to open notes. Ctrl+S saves the editor.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.set_mode("note")
        self.update_theme_button()

    def update_theme_button(self) -> None:
        if self.window.theme_mode == "dark":
            self.theme_button.setText("Light")
        else:
            self.theme_button.setText("Dark")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        for key, button in self.buttons.items():
            button.setChecked(key == mode)
            button.setObjectName("Primary" if key == mode else "Ghost")
            button.style().unpolish(button)
            button.style().polish(button)
        self.new_note.setVisible(mode == "note")
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        query = self.search.text().strip().lower()
        if self.mode == "note":
            self._load_notes(query)
        elif self.mode == "task":
            self._load_tasks(query)
        elif self.mode == "goal":
            self._load_goals(query)
        elif self.mode == "project":
            self._load_projects(query)
        elif self.mode == "reports":
            self._load_reports(query)
        else:
            self._load_trash(query)

    def open_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, value = data
        self.open_capture(kind, value)

    def open_capture(self, kind: str, value) -> None:
        if kind == "note":
            self.window.open_note_day(parse_day(str(value)))
        elif kind == "task":
            self.window.open_task(int(value))
        elif kind == "goal":
            self.window.open_goal(int(value))
        elif kind == "project":
            self.window.open_project(int(value))

    def remove_capture(self, kind: str, value) -> None:
        if kind == "note":
            day = parse_day(str(value))
            reflection = self.window.repo.reflection(day)
            body = reflection.note or reflection.short_reflection
            if body.strip():
                _trash_add(
                    self.window.repo.conn,
                    "note",
                    date_key(day),
                    _folder_label(day),
                    body,
                    {"short_reflection": reflection.short_reflection, **_note_meta(self.window.repo.conn, date_key(day))},
                )
            reflection.note = ""
            reflection.short_reflection = ""
            self.window.repo.save_reflection(reflection)
            if self.window.notebook.current_kind == "note" and self.window.notebook.current_day == day:
                self.window.notebook.load_note_day(day)
            self.window.preview.setText(f"Moved notes for {date_key(day)} to Trash.")
        elif kind == "task":
            task = self.window.repo.task(int(value))
            _trash_add(
                self.window.repo.conn,
                "task",
                str(task.id),
                task.title,
                task.note,
                {
                    "day": date_key(task.day),
                    "status": task.status,
                    "planned_time": task.planned_time,
                    "carry_forward": task.carry_forward,
                },
            )
            self.window.repo.archive_task(int(value))
            if self.window.notebook.current_kind == "task" and self.window.notebook.current_id == int(value):
                self.window.notebook.load_note_day(today())
            self.window.preview.setText("Moved task to Trash.")
        elif kind == "goal":
            goal = self.window.repo.goal(int(value))
            _trash_add(
                self.window.repo.conn,
                "goal",
                str(goal.id),
                goal.title,
                goal.note,
                {"created_on": date_key(goal.created_on), "archived_on": date_key(goal.archived_on) if goal.archived_on else ""},
            )
            self.window.repo.archive_goal(int(value), today())
            if self.window.notebook.current_kind == "goal" and self.window.notebook.current_id == int(value):
                self.window.notebook.load_note_day(today())
            self.window.preview.setText("Moved goal to Trash.")
        elif kind == "project":
            self.window.repo.conn.execute(
                "UPDATE projects SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(value),),
            )
            self.window.repo.conn.commit()
            if self.window.notebook.current_kind == "project" and self.window.notebook.current_id == int(value):
                self.window.notebook.load_note_day(today())
            self.window.preview.setText("Archived project.")
        self.window.store.data_changed.emit()

    def restore_trash(self, trash_id: int) -> None:
        row = self.window.repo.conn.execute("SELECT * FROM trash_items WHERE id = ?", (trash_id,)).fetchone()
        if row is None:
            return
        metadata = _json_load(row["metadata"])
        if row["kind"] == "note":
            day = parse_day(row["item_key"])
            reflection = self.window.repo.reflection(day)
            reflection.note = row["body"]
            reflection.short_reflection = str(metadata.get("short_reflection", ""))
            self.window.repo.save_reflection(reflection)
            _set_note_meta(
                self.window.repo.conn,
                date_key(day),
                int(metadata.get("pinned", 0)),
                str(metadata.get("tags", "")),
            )
            self.window.open_note_day(day)
        elif row["kind"] == "task":
            task_id = int(row["item_key"])
            status = str(metadata.get("status", OPEN))
            try:
                self.window.repo.set_task_status(task_id, status)
                self.window.repo.set_task_note(task_id, row["body"])
                self.window.open_task(task_id)
            except KeyError:
                task = self.window.repo.add_task(
                    row["title"],
                    parse_day(str(metadata.get("day", date_key(today())))),
                    bool(metadata.get("carry_forward", False)),
                    str(metadata.get("planned_time", "")),
                )
                self.window.repo.set_task_note(task.id, row["body"])
                self.window.open_task(task.id)
        elif row["kind"] == "goal":
            goal_id = int(row["item_key"])
            try:
                self.window.repo.conn.execute("UPDATE goals SET archived_on = NULL WHERE id = ?", (goal_id,))
                self.window.repo.conn.commit()
                self.window.open_goal(goal_id)
            except KeyError:
                goal = self.window.repo.add_goal(row["title"], created_on=parse_day(str(metadata.get("created_on", date_key(today())))))
                self.window.repo.set_goal_note(goal.id, row["body"])
                self.window.open_goal(goal.id)
        self.window.repo.conn.execute("DELETE FROM trash_items WHERE id = ?", (trash_id,))
        self.window.repo.conn.commit()
        self.window.preview.setText("Restored from trash.")
        self.window.store.data_changed.emit()

    def delete_trash(self, trash_id: int) -> None:
        self.window.repo.conn.execute("DELETE FROM trash_items WHERE id = ?", (trash_id,))
        self.window.repo.conn.commit()
        self.window.preview.setText("Deleted from trash.")
        self.refresh()

    def _load_notes(self, query: str) -> None:
        seen: set[str] = set()
        today_key = date_key(today())
        rows = self.window.repo.conn.execute(
            """
            SELECT r.day, r.note, r.short_reflection, r.updated_at,
                   COALESCE(m.pinned, 0) AS pinned,
                   COALESCE(m.tags, '') AS tags
            FROM reflections r
            LEFT JOIN note_metadata m ON m.day = r.day
            WHERE r.note != '' OR r.short_reflection != ''
            ORDER BY COALESCE(m.pinned, 0) DESC, r.day DESC
            LIMIT 300
            """
        ).fetchall()
        if not rows:
            self._add_row("note", today_key, "Today", "Empty note")
            return
        if today_key not in {row["day"] for row in rows}:
            self._add_row("note", today_key, "Today", "Empty note")
            seen.add(today_key)
        current_group = ""
        pinned_header_added = False
        for row in rows:
            day_key = row["day"]
            if day_key in seen:
                continue
            text = row["note"] or row["short_reflection"] or ""
            day = parse_day(day_key)
            if row["pinned"]:
                if not pinned_header_added:
                    self._add_header("Pinned")
                    pinned_header_added = True
            else:
                group = f"{day:%Y} / {day:%B}"
                if group != current_group:
                    self._add_header(group)
                    current_group = group
            tags = str(row["tags"] or "") or _tags_for_text(text)
            title = _folder_label(day)
            snippet = _snippet(text) or "Empty note"
            haystack = f"{day_key} {title} {snippet} {tags}".lower()
            if query and query not in haystack:
                continue
            detail = _note_detail(snippet, tags, bool(row["pinned"]))
            self._add_row("note", day_key, title, detail)
            seen.add(day_key)

    def _load_tasks(self, query: str) -> None:
        rows = self.window.repo.conn.execute(
            """
            SELECT id, title, day, status, planned_time FROM daily_tasks
            WHERE status != 'archived'
            ORDER BY day DESC, id DESC
            LIMIT 300
            """
        ).fetchall()
        for row in rows:
            detail = f"{row['day']} - {row['status']}"
            if row["planned_time"]:
                detail = f"{detail} at {row['planned_time']}"
            haystack = f"{row['title']} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_row("task", row["id"], row["title"], detail)

    def _load_goals(self, query: str) -> None:
        for goal in self.window.repo.active_goals():
            detail = f"active - created {date_key(goal.created_on)}"
            haystack = f"{goal.title} {goal.note} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_row("goal", goal.id, goal.title, detail)

    def _load_projects(self, query: str) -> None:
        rows = self.window.repo.conn.execute(
            """
            SELECT p.*,
                   COUNT(e.id) AS entry_count
            FROM projects p
            LEFT JOIN engineering_entries e ON e.project_id = p.id
            WHERE p.status = 'active'
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.name ASC
            LIMIT 300
            """
        ).fetchall()
        for row in rows:
            detail = f"{row['entry_count']} engineering entries"
            haystack = f"{row['name']} {row['note']} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_row("project", row["id"], row["name"], detail)

    def _load_trash(self, query: str) -> None:
        rows = self.window.repo.conn.execute(
            """
            SELECT * FROM trash_items
            ORDER BY deleted_at DESC, id DESC
            LIMIT 300
            """
        ).fetchall()
        for row in rows:
            detail = f"{row['kind']} - removed {row['deleted_at'][:10]}"
            haystack = f"{row['kind']} {row['title']} {row['body']} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_trash_row(row["id"], row["title"], detail)

    def _load_reports(self, query: str) -> None:
        actions = [
            ("Weekly Summary", "Export the normal Momentum weekly summary.", self.window.export_week),
            ("Daily Standup", "Yesterday, today, and blockers as Markdown.", self.window.export_standup),
            ("Engineering Report", "Shipped, decisions, bugs, blockers, learning, meetings, snippets.", self.window.export_engineering_report),
            ("Command Palette", "Open Ctrl+K actions and quick capture.", self.window.open_command_palette),
        ]
        self._add_header("Exports")
        for title, detail, action in actions:
            haystack = f"{title} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_action_row(title, detail, action)
        rows = self.window.repo.conn.execute(
            """
            SELECT e.*, p.name AS project_name
            FROM engineering_entries e
            LEFT JOIN projects p ON p.id = e.project_id
            ORDER BY e.day DESC, e.id DESC
            LIMIT 12
            """
        ).fetchall()
        if rows:
            self._add_header("Recent Engineering")
        for row in rows:
            detail = f"{row['entry_type']} - {row['day']}"
            if row["project_name"]:
                detail = f"{detail} - {row['project_name']}"
            haystack = f"{row['title']} {detail}".lower()
            if query and query not in haystack:
                continue
            self._add_static_row(row["title"], detail)

    def _add_row(self, kind: str, value, title: str, detail: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, (kind, value))
        self.list.addItem(item)
        row = LibraryRow(self, kind, value, title, detail)
        item.setSizeHint(_row_size_hint(row))
        self.list.setItemWidget(item, row)

    def _add_trash_row(self, trash_id: int, title: str, detail: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, ("trash", trash_id))
        self.list.addItem(item)
        row = TrashRow(self, trash_id, title, detail)
        item.setSizeHint(_row_size_hint(row))
        self.list.setItemWidget(item, row)

    def _add_action_row(self, title: str, detail: str, action) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)
        self.list.addItem(item)
        row = ActionRow(title, detail, action)
        item.setSizeHint(_row_size_hint(row))
        self.list.setItemWidget(item, row)

    def _add_static_row(self, title: str, detail: str) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.ItemIsEnabled)
        self.list.addItem(item)
        row = StaticLibraryRow(title, detail)
        item.setSizeHint(_row_size_hint(row))
        self.list.setItemWidget(item, row)

    def _add_header(self, label: str) -> None:
        item = QListWidgetItem()
        item.setFlags(Qt.NoItemFlags)
        self.list.addItem(item)
        header = QLabel(label)
        header.setObjectName("LibraryHeader")
        item.setSizeHint(QSize(0, header.sizeHint().height()))
        self.list.setItemWidget(item, header)


class LibraryRow(QFrame):
    def __init__(self, sidebar: LibrarySidebar, kind: str, value, title: str, detail: str):
        super().__init__()
        self.sidebar = sidebar
        self.kind = kind
        self.value = value
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        open_button = QPushButton(f"{title}\n{detail}")
        open_button.setObjectName("LibraryOpen")
        open_button.setToolTip("Open")
        open_button.setMinimumWidth(0)
        open_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        open_button.clicked.connect(lambda _checked=False: sidebar.open_capture(kind, value))
        layout.addWidget(open_button, 1)

        more = QPushButton("...")
        more.setObjectName("MoreButton")
        more.setFixedWidth(38)
        more.setToolTip("More actions")
        more.clicked.connect(self.open_menu)
        layout.addWidget(more)

    def open_menu(self) -> None:
        menu = QMenu(self)
        edit = menu.addAction("Edit")
        delete = menu.addAction("Delete")
        action = menu.exec(self.mapToGlobal(self.rect().bottomRight()))
        if action == edit:
            self.sidebar.open_capture(self.kind, self.value)
        elif action == delete:
            self.sidebar.remove_capture(self.kind, self.value)


class TrashRow(QFrame):
    def __init__(self, sidebar: LibrarySidebar, trash_id: int, title: str, detail: str):
        super().__init__()
        self.sidebar = sidebar
        self.trash_id = trash_id
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)

        label = QLabel(f"{title}\n{detail}")
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        layout.addWidget(label, 1)

        more = QPushButton("...")
        more.setObjectName("MoreButton")
        more.setFixedWidth(38)
        more.setToolTip("More actions")
        more.clicked.connect(self.open_menu)
        layout.addWidget(more)

    def open_menu(self) -> None:
        menu = QMenu(self)
        restore = menu.addAction("Restore")
        delete = menu.addAction("Delete Forever")
        action = menu.exec(self.mapToGlobal(self.rect().bottomRight()))
        if action == restore:
            self.sidebar.restore_trash(self.trash_id)
        elif action == delete:
            self.sidebar.delete_trash(self.trash_id)


class ActionRow(QFrame):
    def __init__(self, title: str, detail: str, action):
        super().__init__()
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(6)
        body = QVBoxLayout()
        label = QLabel(title)
        label.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        meta.setWordWrap(True)
        body.addWidget(label)
        body.addWidget(meta)
        layout.addLayout(body, 1)
        run = QPushButton("Run")
        run.setObjectName("Primary")
        run.clicked.connect(action)
        layout.addWidget(run)


class StaticLibraryRow(QFrame):
    def __init__(self, title: str, detail: str):
        super().__init__()
        self.setObjectName("LibraryRow")
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        label = QLabel(title)
        label.setWordWrap(True)
        meta = QLabel(detail)
        meta.setObjectName("Caption")
        meta.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(meta)


class LibraryEditorCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("InsightCard")
        self.window = window
        self.current_kind = "note"
        self.current_id: int | None = None
        self.current_day = today()
        self._loading = False
        self._dirty = False

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(900)
        self.autosave_timer.timeout.connect(self.save_current)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.title = QLabel("Notes")
        self.title.setObjectName("SectionTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.meta = QLabel("")
        self.meta.setObjectName("Caption")
        header.addWidget(self.meta)
        self.pin = QPushButton("Pin")
        self.pin.setObjectName("Ghost")
        self.pin.clicked.connect(self.toggle_pin)
        header.addWidget(self.pin)
        focus = QPushButton("Focus")
        focus.setObjectName("Ghost")
        focus.clicked.connect(window.toggle_focus_mode)
        header.addWidget(focus)
        today_button = QPushButton("Today")
        today_button.setObjectName("Ghost")
        today_button.clicked.connect(lambda: self.load_note_day(today()))
        header.addWidget(today_button)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_current)
        header.addWidget(save)
        layout.addLayout(header)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Title")
        self.name.textChanged.connect(self.schedule_autosave)
        layout.addWidget(self.name)

        self.tags = QLabel("")
        self.tags.setObjectName("Caption")
        self.tags.setWordWrap(True)
        layout.addWidget(self.tags)

        self.editor = QTextEdit()
        self.editor.setObjectName("NotebookEditor")
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText("Write anything here. This is your local notebook.")
        self.editor.textChanged.connect(self.schedule_autosave)
        layout.addWidget(self.editor)

        self.status = QLabel("Ready.")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        self.related = RelatedPanel(window)
        layout.addWidget(self.related)

        self.load_note_day(today())

    def load_note_day(self, day: date) -> None:
        self._loading = True
        self.current_kind = "note"
        self.current_id = None
        self.current_day = day
        reflection = self.window.repo.reflection(day)
        meta = _note_meta(self.window.repo.conn, date_key(day))
        self.title.setText("Notes")
        self.meta.setText(_folder_label(day))
        self.pin.setVisible(True)
        self.pin.setText("Unpin" if meta["pinned"] else "Pin")
        self.pin.setObjectName("Primary" if meta["pinned"] else "Ghost")
        self.pin.style().unpolish(self.pin)
        self.pin.style().polish(self.pin)
        self.name.setVisible(False)
        self.editor.setPlaceholderText("Write anything here. This is your local notebook.")
        self.editor.setPlainText(reflection.note)
        self.tags.setText(_tag_line(meta["tags"] or _tags_for_text(reflection.note)))
        self.status.setText("Auto-save is on.")
        self.related.refresh_for(reflection.note)
        self._dirty = False
        self._loading = False

    def load_task(self, task_id: int) -> None:
        self._loading = True
        task = self.window.repo.task(task_id)
        self.current_kind = "task"
        self.current_id = task.id
        self.current_day = task.day
        self.title.setText("Task")
        self.meta.setText(f"{date_key(task.day)} - {task.status}")
        self.pin.setVisible(False)
        self.name.setVisible(True)
        self.name.setText(task.title)
        self.editor.setPlaceholderText("Task notes...")
        self.editor.setPlainText(task.note)
        self.tags.setText(_tag_line(_tags_for_text(f"{task.title} {task.note}")))
        self.status.setText("Auto-save is on.")
        self.related.refresh_for(f"{task.title} {task.note}")
        self._dirty = False
        self._loading = False

    def load_goal(self, goal_id: int) -> None:
        self._loading = True
        goal = self.window.repo.goal(goal_id)
        self.current_kind = "goal"
        self.current_id = goal.id
        self.current_day = goal.created_on
        self.title.setText("Goal")
        state = "archived" if goal.archived_on else "active"
        self.meta.setText(f"{state} - created {date_key(goal.created_on)}")
        self.pin.setVisible(False)
        self.name.setVisible(True)
        self.name.setText(goal.title)
        self.editor.setPlaceholderText("Goal notes...")
        self.editor.setPlainText(goal.note)
        self.tags.setText(_tag_line(_tags_for_text(f"{goal.title} {goal.note}")))
        self.status.setText("Auto-save is on.")
        self.related.refresh_for(f"{goal.title} {goal.note}")
        self._dirty = False
        self._loading = False

    def load_project(self, project_id: int) -> None:
        self._loading = True
        row = self.window.repo.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            self._loading = False
            return
        self.current_kind = "project"
        self.current_id = int(row["id"])
        self.current_day = today()
        self.title.setText("Project")
        self.meta.setText(row["status"])
        self.pin.setVisible(False)
        self.name.setVisible(True)
        self.name.setText(row["name"])
        self.editor.setPlaceholderText("Project notes, context, links, risks...")
        self.editor.setPlainText(row["note"])
        self.tags.setText(_tag_line(_tags_for_text(f"{row['name']} {row['note']}")))
        self.status.setText("Auto-save is on.")
        self.related.refresh_for(f"{row['name']} {row['note']}")
        self._dirty = False
        self._loading = False

    def schedule_autosave(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self.status.setText("Saving...")
        self.autosave_timer.start()

    def toggle_pin(self) -> None:
        if self.current_kind != "note":
            return
        day_key = date_key(self.current_day)
        meta = _note_meta(self.window.repo.conn, day_key)
        _set_note_meta(self.window.repo.conn, day_key, 0 if meta["pinned"] else 1, meta["tags"])
        self.load_note_day(self.current_day)
        self.window.store.data_changed.emit()

    def set_focus_mode(self, enabled: bool) -> None:
        self.title.setText("Focus Notes" if enabled and self.current_kind == "note" else self.current_kind.title() + "s" if self.current_kind == "note" else self.current_kind.title())

    def save_current(self) -> None:
        if self._loading:
            return
        text = self.editor.toPlainText().strip()
        if self.current_kind == "note":
            reflection = self.window.repo.reflection(self.current_day)
            reflection.note = text
            self.window.repo.save_reflection(reflection)
            day_key = date_key(self.current_day)
            meta = _note_meta(self.window.repo.conn, day_key)
            tags = _tags_for_text(text)
            _set_note_meta(self.window.repo.conn, day_key, meta["pinned"], tags)
            self.tags.setText(_tag_line(tags))
            self.status.setText(f"Saved notes for {date_key(self.current_day)}.")
        elif self.current_kind == "task" and self.current_id is not None:
            title = self.name.text().strip()
            if title:
                self.window.repo.update_task_title(self.current_id, title)
            self.window.repo.set_task_note(self.current_id, text)
            self.tags.setText(_tag_line(_tags_for_text(f"{title} {text}")))
            self.status.setText("Task saved.")
        elif self.current_kind == "goal" and self.current_id is not None:
            title = self.name.text().strip()
            if title:
                self.window.repo.update_goal_title(self.current_id, title)
            self.window.repo.set_goal_note(self.current_id, text)
            self.tags.setText(_tag_line(_tags_for_text(f"{title} {text}")))
            self.status.setText("Goal saved.")
        elif self.current_kind == "project" and self.current_id is not None:
            name = self.name.text().strip()
            if name:
                self.window.repo.conn.execute(
                    """
                    UPDATE projects
                    SET name = ?, note = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (name, text, self.current_id),
                )
                self.window.repo.conn.commit()
            self.tags.setText(_tag_line(_tags_for_text(f"{name} {text}")))
            self.status.setText("Project saved.")
        self._dirty = False
        self.window.store.data_changed.emit()


class RelatedPanel(QFrame):
    def __init__(self, window: CaptureWindow):
        super().__init__()
        self.window = window
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title = QLabel("Related Notes")
        title.setObjectName("Caption")
        layout.addWidget(title)
        self.items = QVBoxLayout()
        self.items.setSpacing(6)
        layout.addLayout(self.items)

    def refresh_for(self, text: str) -> None:
        _clear_layout(self.items)
        terms = _query_terms(text)
        if not terms:
            self._add("Related notes appear here while you write.")
            return
        like = [f"%{term}%" for term in terms[:4]]
        clauses = " OR ".join(["note LIKE ? OR short_reflection LIKE ?"] * len(like))
        params = []
        for value in like:
            params.extend([value, value])
        rows = self.window.repo.conn.execute(
            f"""
            SELECT day, note, short_reflection FROM reflections
            WHERE ({clauses}) AND (note != '' OR short_reflection != '')
            ORDER BY day DESC
            LIMIT 4
            """,
            params,
        ).fetchall()
        if not rows:
            self._add("No related notes yet.")
            return
        for row in rows:
            body = row["note"] or row["short_reflection"]
            self._add(f"{row['day']} - {_snippet(body, 120)}")

    def _add(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        self.items.addWidget(label)


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


class CommandPalette(QDialog):
    def __init__(self, window: CaptureWindow):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Command Palette")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command or capture text...")
        layout.addWidget(self.input)
        commands = [
            ("New Today Note", lambda: window.open_note_day(today())),
            ("Focus Mode", window.toggle_focus_mode),
            ("Export Standup", window.export_standup),
            ("Export Engineering Report", window.export_engineering_report),
            ("Open Trash", lambda: window.library.set_mode("trash")),
            ("Open Projects", lambda: window.library.set_mode("project")),
        ]
        for label, action in commands:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=action: self._run(fn))
            layout.addWidget(button)
        self.input.returnPressed.connect(self.capture_text)

    def _run(self, action) -> None:
        action()
        self.accept()

    def capture_text(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.window.capture.input.setPlainText(text)
        self.window.submit()
        self.accept()


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
        carry.clicked.connect(window.carry_open_tasks)
        review.addWidget(carry)
        skip = QPushButton("Skip Open")
        skip.setObjectName("Ghost")
        skip.clicked.connect(window.skip_open_tasks)
        review.addWidget(skip)
        export = QPushButton("Export Week")
        export.setObjectName("Ghost")
        export.clicked.connect(window.export_week)
        review.addWidget(export)
        layout.addLayout(review)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search notes, tasks, goals...")
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
            button.clicked.connect(lambda _checked=False, value=preset: self.set_preset(value))
            self.buttons[preset] = button
            header.addWidget(button)
        layout.addLayout(header)

        custom = QHBoxLayout()
        custom.addWidget(QLabel("From"))
        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        custom.addWidget(self.start_edit)
        custom.addWidget(QLabel("To"))
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        custom.addWidget(self.end_edit)
        apply_button = QPushButton("Apply")
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


def _append_text(existing: str, value: str) -> str:
    value = value.strip()
    if not existing.strip():
        return value
    return f"{existing.rstrip()}\n{value}"


def _remove_appended_text(existing: str, value: str) -> str:
    value = value.strip()
    lines = existing.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip() == value:
            del lines[index]
            break
    return "\n".join(line for line in lines).strip()


ENGINEERING_TYPES = {
    "decision": ("decision", "decide", "decided", "adr"),
    "bug": ("bug", "error", "issue", "broken", "fix", "regression"),
    "snippet": ("snippet", "command", "cmd", "code", "script"),
    "meeting": ("meeting", "sync", "standup", "1:1", "call"),
    "blocker": ("blocker", "blocked", "stuck", "risk"),
    "learning": ("learned", "learning", "study", "read"),
    "ship": ("shipped", "release", "deploy", "merged", "pr"),
}


def _project_for_text(conn, text: str) -> int | None:
    name = _extract_project_name(conn, text)
    if not name:
        return None
    row = conn.execute("SELECT id FROM projects WHERE lower(name) = lower(?)", (name,)).fetchone()
    if row:
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        conn.commit()
        return int(row["id"])
    cur = conn.execute("INSERT INTO projects (name) VALUES (?)", (name,))
    conn.commit()
    return int(cur.lastrowid)


def _extract_project_name(conn, text: str) -> str:
    lowered = text.lower()
    markers = ("project:", "project ", "for project ", "on project ")
    for marker in markers:
        if marker in lowered:
            index = lowered.index(marker) + len(marker)
            raw = text[index:].strip(" :-")
            name = []
            for word in raw.split():
                clean = word.strip(",.;:")
                if clean.lower() in {"decision", "bug", "task", "note", "goal", "to", "for", "about"} and name:
                    break
                name.append(clean)
                if len(name) >= 4:
                    break
            if name:
                return " ".join(name).strip().title()
    rows = conn.execute("SELECT name FROM projects WHERE status = 'active' ORDER BY updated_at DESC LIMIT 100").fetchall()
    for row in rows:
        name = row["name"]
        if name.lower() in lowered:
            return name
    if "capgemini" in lowered:
        return "Capgemini"
    if "momentum" in lowered or "focus tracker" in lowered:
        return "Momentum"
    if "job search" in lowered or "linkedin" in lowered or "resume" in lowered:
        return "Job Search"
    return ""


def _link_capture_project(conn, capture_event_id: int, project_id: int, entity_type: str, entity_id: int | None) -> None:
    conn.execute(
        """
        INSERT INTO capture_project_links (capture_event_id, project_id, entity_type, entity_id)
        VALUES (?, ?, ?, ?)
        """,
        (capture_event_id, project_id, entity_type, entity_id),
    )
    conn.commit()


def _record_engineering_entry(conn, intent: CaptureIntent, project_id: int | None) -> None:
    entry_type, title, body = _engineering_entry(intent.text)
    if not entry_type:
        return
    conn.execute(
        """
        INSERT INTO engineering_entries (entry_type, title, body, day, project_id, source_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (entry_type, title, body, date_key(intent.day), project_id, intent.raw),
    )
    conn.commit()


def _engineering_entry(text: str) -> tuple[str, str, str]:
    stripped = text.strip()
    lowered = stripped.lower()
    for entry_type, aliases in ENGINEERING_TYPES.items():
        for alias in aliases:
            for separator in (":", "-"):
                prefix = f"{alias}{separator}"
                if lowered.startswith(prefix):
                    title = stripped[len(prefix):].strip()
                    return entry_type, title or stripped, stripped
                marker = f" {prefix}"
                if marker in lowered:
                    index = lowered.index(marker) + len(marker)
                    title = stripped[index:].strip()
                    return entry_type, title or stripped, stripped
    if any(word in lowered for word in ("pull request", "pr ", "merged", "deploy", "release")):
        return "ship", stripped, stripped
    if any(word in lowered for word in ("blocked", "blocker", "stuck")):
        return "blocker", stripped, stripped
    return "", "", ""


def _export_standup(conn, repo: Repository):
    folder = BASE_DIR / "momentum_captures" / f"{today():%Y}" / f"{today():%m-%B}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"standup-{date_key(today())}.md"
    yesterday = today() - timedelta(days=1)
    done = [
        task.title
        for task in repo.tasks_for_day(yesterday)
        if task.status == DONE
    ]
    today_tasks = [task.title for task in repo.tasks_for_day(today()) if task.status == OPEN]
    blockers = _entries(conn, "blocker", today() - timedelta(days=7), today())
    shipped = _entries(conn, "ship", today() - timedelta(days=7), today())
    lines = [
        f"# Standup - {date_key(today())}",
        "",
        "## Yesterday",
        *[f"- {item}" for item in (done or shipped or ["No completed work captured yet."])],
        "",
        "## Today",
        *[f"- {item}" for item in (today_tasks or ["No open tasks captured yet."])],
        "",
        "## Blockers",
        *[f"- {item}" for item in (blockers or ["No blockers captured."])],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _export_engineering_report(conn):
    folder = BASE_DIR / "momentum_captures" / f"{today():%Y}" / f"{today():%m-%B}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"engineering-report-{date_key(today())}.md"
    start = today() - timedelta(days=6)
    sections = [
        ("Shipped", "ship"),
        ("Decisions", "decision"),
        ("Bugs / Issues", "bug"),
        ("Blockers / Risks", "blocker"),
        ("Learning", "learning"),
        ("Meetings", "meeting"),
        ("Snippets / Commands", "snippet"),
    ]
    lines = [f"# Engineering Report - {date_key(start)} to {date_key(today())}", ""]
    for title, entry_type in sections:
        lines.extend([f"## {title}", ""])
        entries = _entries(conn, entry_type, start, today())
        lines.extend(f"- {item}" for item in (entries or ["None captured."]))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _entries(conn, entry_type: str, start: date, end: date) -> list[str]:
    rows = conn.execute(
        """
        SELECT e.title, e.day, p.name AS project_name
        FROM engineering_entries e
        LEFT JOIN projects p ON p.id = e.project_id
        WHERE e.entry_type = ? AND e.day BETWEEN ? AND ?
        ORDER BY e.day DESC, e.id DESC
        LIMIT 20
        """,
        (entry_type, date_key(start), date_key(end)),
    ).fetchall()
    result = []
    for row in rows:
        prefix = f"{row['project_name']}: " if row["project_name"] else ""
        result.append(f"{row['day']} - {prefix}{row['title']}")
    return result


def _json_load(value: str) -> dict:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _trash_add(conn, kind: str, item_key: str, title: str, body: str, metadata: dict) -> None:
    conn.execute(
        """
        INSERT INTO trash_items (kind, item_key, title, body, metadata)
        VALUES (?, ?, ?, ?, ?)
        """,
        (kind, item_key, title, body, json.dumps(metadata, sort_keys=True)),
    )
    conn.commit()


def _note_meta(conn, day_key: str) -> dict:
    row = conn.execute("SELECT pinned, tags FROM note_metadata WHERE day = ?", (day_key,)).fetchone()
    if row is None:
        return {"pinned": 0, "tags": ""}
    return {"pinned": int(row["pinned"]), "tags": row["tags"]}


def _set_note_meta(conn, day_key: str, pinned: int, tags: str) -> None:
    conn.execute(
        """
        INSERT INTO note_metadata (day, pinned, tags, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(day) DO UPDATE SET
            pinned = excluded.pinned,
            tags = excluded.tags,
            updated_at = CURRENT_TIMESTAMP
        """,
        (day_key, int(bool(pinned)), tags.strip()),
    )
    conn.commit()


def _tags_for_text(value: str) -> str:
    lowered = value.lower()
    rules = {
        "job": ("job", "career", "interview", "resume", "capgemini", "linkedin", "apply"),
        "health": ("health", "exercise", "gym", "walk", "sleep", "doctor", "medicine"),
        "money": ("money", "budget", "bill", "pay", "salary", "expense", "bank"),
        "learning": ("learn", "study", "course", "practice", "read", "training"),
        "project": ("project", "build", "ship", "feature", "bug", "release"),
        "people": ("call", "meet", "friend", "family", "message", "email"),
        "idea": ("idea", "maybe", "concept", "strategy", "roadmap", "plan"),
    }
    tags = [name for name, words in rules.items() if any(word in lowered for word in words)]
    return ", ".join(tags[:4])


def _query_terms(value: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "today", "tomorrow", "note", "task"}
    terms = []
    for raw in value.lower().replace(":", " ").replace("-", " ").split():
        term = "".join(ch for ch in raw if ch.isalnum())
        if len(term) >= 3 and term not in stop:
            terms.append(term)
    return list(dict.fromkeys(terms))[:6]


def _tag_line(tags: str) -> str:
    return f"Tags: {tags}" if tags.strip() else "Tags: none yet"


def _note_detail(snippet: str, tags: str, pinned: bool) -> str:
    pieces = []
    if pinned:
        pieces.append("Pinned")
    if tags:
        pieces.append(f"Tags: {tags}")
    pieces.append(snippet)
    return " - ".join(pieces)


def _folder_label(day: date) -> str:
    if day == today():
        return f"Today - {date_key(day)}"
    return f"{day:%Y} / {day:%B} / {day:%d}"


def _snippet(value: str, limit: int = 110) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget:
            widget.deleteLater()
        elif child_layout:
            _clear_layout(child_layout)


def _row_size_hint(row: QWidget) -> QSize:
    return QSize(0, max(row.sizeHint().height(), row.minimumHeight()))


def _to_qdate(value) -> QDate:
    return QDate(value.year, value.month, value.day)


def _from_qdate(value: QDate):
    return value.toPython()
