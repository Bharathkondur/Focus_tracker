from __future__ import annotations

from datetime import date

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout

from momentum.core.dates import date_key, today
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.utils import (
    _clear_layout,
    _folder_label,
    _note_meta,
    _query_terms,
    _set_note_meta,
    _snippet,
    _tag_line,
    _tags_for_text,
)
from momentum.ui.widgets.cards import Card


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
        _accessible(self.pin, "Pin note")
        self.pin.clicked.connect(self.toggle_pin)
        header.addWidget(self.pin)
        focus = QPushButton("Focus")
        focus.setObjectName("Ghost")
        _accessible(focus, "Focus editor")
        focus.clicked.connect(window.toggle_focus_mode)
        header.addWidget(focus)
        today_button = QPushButton("Today")
        today_button.setObjectName("Ghost")
        _accessible(today_button, "Open today's note")
        today_button.clicked.connect(lambda: self.load_note_day(today()))
        header.addWidget(today_button)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        _accessible(save, "Save current note")
        save.clicked.connect(self.save_current)
        header.addWidget(save)
        layout.addLayout(header)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Title")
        _accessible(self.name, "Note title")
        self.name.textChanged.connect(self.schedule_autosave)
        layout.addWidget(self.name)

        self.tags = QLabel("")
        self.tags.setObjectName("Caption")
        self.tags.setWordWrap(True)
        layout.addWidget(self.tags)

        self.editor = QTextEdit()
        self.editor.setObjectName("NotebookEditor")
        _accessible(self.editor, "Notebook editor", "Write and edit local notes")
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
