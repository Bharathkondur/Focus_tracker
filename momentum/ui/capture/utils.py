from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from PySide6.QtCore import QDate, QSize
from PySide6.QtWidgets import QWidget

from momentum.capture.intent import CaptureIntent
from momentum.core.dates import date_key, today
from momentum.data.paths import BASE_DIR
from momentum.data.repository import DONE, OPEN, Repository


logger = logging.getLogger(__name__)


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
        logger.exception("Failed to decode stored JSON metadata")
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
