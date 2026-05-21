from __future__ import annotations

import os
import webbrowser
from datetime import date, timedelta
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QApplication,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from momentum.capture.files import append_capture, export_weekly_summary
from momentum.capture.intent import CaptureIntent
from momentum.capture.memory import CaptureMemory, CaptureRecord
from momentum.capture.router import ContextRouter, RoutedCapture
from momentum.core.dates import date_key, parse_day, today
from momentum.data.paths import BASE_DIR
from momentum.data.repository import DONE, OPEN, SKIPPED
from momentum.data.repository import Repository
from momentum.data.safety import create_backup, create_support_bundle, export_sql
from momentum.state.store import AppStore
from momentum.ui.theme import load_stylesheet
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.async_model import AsyncIntentPredictor, AsyncIntentResult
from momentum.ui.capture.cards import (
    CaptureCard,
    EngineeringCard,
    SaveActionBar,
    SummaryCard,
    TimelineCard,
    WorkspaceCard,
)
from momentum.ui.capture.dialogs import CommandPalette, OnboardingDialog, SettingsDialog
from momentum.ui.capture.editor import LibraryEditorCard
from momentum.ui.capture.sidebar import LibrarySidebar
from momentum.ui.capture.utils import (
    _append_text,
    _export_engineering_report,
    _export_standup,
    _link_capture_project,
    _project_for_text,
    _record_engineering_entry,
    _remove_appended_text,
)



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
        self.async_predictor = AsyncIntentPredictor(self.router.local_model)
        self.async_predictor.finished.connect(self._handle_model_prediction)
        self.forced_kind = "auto"
        self.last_route: RoutedCapture | None = None
        self.last_save: LastSave | None = None
        self._model_request_id = 0
        self._model_prediction_text = ""
        self._model_prediction = None
        self.focus_mode = False
        self.theme_mode = self.repo.setting("theme", "dark") or "dark"

        self.setWindowTitle("Momentum Capture")
        _accessible(self, "Momentum Capture", "Local notes, tasks, and goals capture app")
        self.resize(1280, 820)
        self.setMinimumSize(1080, 720)

        root = QWidget()
        root.setObjectName("Root")
        _accessible(root, "Momentum Capture main window")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.library = LibrarySidebar(self)
        shell.addWidget(self.library)

        scroll = QScrollArea()
        _accessible(scroll, "Main content")
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
        _accessible(self.preview, "Capture status")
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
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(self.open_support_settings)
        QTimer.singleShot(350, self.show_onboarding_if_needed)

    def set_kind(self, kind: str) -> None:
        self.forced_kind = kind
        self.capture.set_active_kind(kind)
        self.update_preview()

    def update_preview(self) -> None:
        route = self._route(allow_model=False)
        self.last_route = route
        if route is None:
            self.preview.setText("Ready.")
            self.capture.set_prediction("", "")
            self._model_prediction_text = ""
            self._model_prediction = None
            return
        self._show_route(route)
        self._queue_model_prediction(route)

    def submit(self) -> None:
        raw_value = self.capture.input.text()
        auto_route = None
        if self.forced_kind != "auto":
            auto_route = self._route_for(raw_value, "auto")
        route = self._route_for(raw_value, self.forced_kind)
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

    def _route(
        self,
        *,
        allow_model: bool = False,
        model_prediction=None,
    ) -> RoutedCapture | None:
        return self._route_for(
            self.capture.input.text(),
            self.forced_kind,
            allow_model=allow_model,
            model_prediction=model_prediction,
        )

    def _route_for(
        self,
        value: str,
        forced_kind: str,
        *,
        allow_model: bool = False,
        model_prediction=None,
    ) -> RoutedCapture | None:
        prediction = model_prediction
        if prediction is None and self._model_prediction_text == value:
            prediction = self._model_prediction
        return self.router.route(
            value,
            today(),
            forced_kind,
            allow_model=allow_model,
            model_prediction=prediction,
        )

    def _show_route(self, route: RoutedCapture) -> None:
        intent = route.intent
        self.capture.set_prediction(intent.kind, self._date_chip(intent))
        if route.needs_confirmation:
            self.preview.setText("Choose the right destination before saving.")
        else:
            self.preview.setText(self._date_chip(intent))

    def _queue_model_prediction(self, route: RoutedCapture) -> None:
        raw = self.capture.input.text()
        if self.forced_kind != "auto" or not raw.strip() or route.source == "explicit_prefix":
            return
        if self._model_prediction_text == raw and self._model_prediction is not None:
            return
        self._model_prediction_text = raw
        self._model_prediction = None
        self._model_request_id = self.async_predictor.predict(route.intent.text)

    def _handle_model_prediction(self, result: AsyncIntentResult) -> None:
        raw = self.capture.input.text()
        if result.request_id != self._model_request_id or raw != self._model_prediction_text:
            return
        self._model_prediction = result.prediction
        if result.prediction is None or self.forced_kind != "auto":
            return
        route = self._route(allow_model=False, model_prediction=result.prediction)
        if route is None:
            return
        self.last_route = route
        self._show_route(route)

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

    def create_database_backup(self) -> None:
        path = create_backup(self.repo.conn)
        self.preview.setText(f"Backup created: {path.name}")

    def export_database_sql(self) -> None:
        path = export_sql(self.repo.conn)
        self.preview.setText(f"Database export created: {path.name}")

    def export_support_bundle(self) -> None:
        path = create_support_bundle(self.repo.conn)
        self.preview.setText(f"Support bundle exported: {path.name}")

    def open_data_folder(self) -> None:
        if hasattr(os, "startfile"):
            os.startfile(BASE_DIR)  # type: ignore[attr-defined]
        else:
            webbrowser.open(BASE_DIR.as_uri())
        self.preview.setText("Opened Momentum data folder.")

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

    def open_support_settings(self) -> None:
        SettingsDialog(self).exec()

    def show_onboarding_if_needed(self) -> None:
        if self.repo.setting("capture_onboarding_seen"):
            return
        dialog = OnboardingDialog(self)
        dialog.exec()
        self.repo.set_setting("capture_onboarding_seen", "1")

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
