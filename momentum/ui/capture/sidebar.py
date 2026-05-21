from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from momentum.core.dates import date_key, parse_day, today
from momentum.data.repository import OPEN
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.sidebar_rows import ActionRow, LibraryRow, StaticLibraryRow, TrashRow
from momentum.ui.capture.utils import (
    _folder_label,
    _json_load,
    _note_detail,
    _note_meta,
    _row_size_hint,
    _set_note_meta,
    _snippet,
    _tags_for_text,
    _trash_add,
)


class LibrarySidebar(QFrame):
    def __init__(self, window: CaptureWindow):
        super().__init__()
        self.window = window
        self.mode = "note"
        self.setObjectName("Sidebar")
        _accessible(self, "Library sidebar", "Browse notes, tasks, goals, projects, reports, and trash")
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
        _accessible(self.theme_button, "Toggle theme")
        self.theme_button.clicked.connect(window.toggle_theme)
        theme_row.addWidget(self.theme_button)
        layout.addLayout(theme_row)

        tabs = QGridLayout()
        tabs.setHorizontalSpacing(8)
        tabs.setVerticalSpacing(8)
        self.buttons: dict[str, QPushButton] = {}
        for index, (label, mode) in enumerate((("Notes", "note"), ("Tasks", "task"), ("Goals", "goal"), ("Projects", "project"), ("Reports", "reports"), ("Trash", "trash"))):
            button = QPushButton(label)
            _accessible(button, f"Open {label}")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=mode: self.set_mode(value))
            self.buttons[mode] = button
            tabs.addWidget(button, index // 3, index % 3)
        layout.addLayout(tabs)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search library...")
        _accessible(self.search, "Search library", "Search notes, tasks, goals, projects, reports, and trash")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.new_note = QPushButton("New Today Note")
        self.new_note.setObjectName("Primary")
        _accessible(self.new_note, "New today note")
        self.new_note.clicked.connect(lambda: self.window.open_note_day(today()))
        layout.addWidget(self.new_note)

        self.list = QListWidget()
        self.list.setObjectName("LibraryList")
        _accessible(self.list, "Library results")
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
            ("Create Backup", "Write a timestamped SQLite backup to the local backups folder.", self.window.create_database_backup),
            ("Export Database", "Write a timestamped SQL export to the local exports folder.", self.window.export_database_sql),
            ("Support Bundle", "Zip logs, runtime info, and a database copy for debugging.", self.window.export_support_bundle),
            ("Open Data Folder", "Open the local folder that contains data, backups, exports, and logs.", self.window.open_data_folder),
            ("Support Settings", "Open backup, export, and support actions in a settings dialog.", self.window.open_support_settings),
            ("Command Palette", "Open Ctrl+K actions and quick capture.", self.window.open_command_palette),
        ]
        self._add_header("Exports And Support")
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
