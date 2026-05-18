from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from sqlite3 import Connection, OperationalError

from momentum.capture.intent import CaptureIntent
from momentum.core.dates import date_key, parse_day, today


@dataclass(slots=True)
class MemoryItem:
    kind: str
    text: str
    day: date
    context: str = ""
    score: float = 0.0


@dataclass(slots=True)
class CaptureRecord:
    intent: CaptureIntent
    confidence: float
    source: str
    entity_type: str = ""
    entity_id: int | None = None
    context: str = ""


class CaptureMemory:
    def __init__(self, conn: Connection):
        self.conn = conn
        self._fts_available = self._has_fts()

    def remember(self, record: CaptureRecord) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO capture_events (
                raw_text, clean_text, kind, day, planned_time,
                entity_type, entity_id, confidence, source, context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.intent.raw,
                record.intent.text,
                record.intent.kind,
                date_key(record.intent.day),
                record.intent.planned_time,
                record.entity_type,
                record.entity_id,
                record.confidence,
                record.source,
                record.context,
            ),
        )
        if self._fts_available:
            self.conn.execute(
                """
                INSERT INTO capture_fts(rowid, raw_text, clean_text, kind, context)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cur.lastrowid,
                    record.intent.raw,
                    record.intent.text,
                    record.intent.kind,
                    record.context,
                ),
            )
        self.conn.commit()
        return int(cur.lastrowid)

    def forget(self, event_id: int) -> None:
        if self._fts_available:
            try:
                self.conn.execute("DELETE FROM capture_fts WHERE rowid = ?", (event_id,))
            except OperationalError:
                pass
        self.conn.execute("DELETE FROM capture_events WHERE id = ?", (event_id,))
        self.conn.commit()

    def remember_correction(self, raw: str, clean: str, predicted: str, corrected: str) -> None:
        if predicted == corrected:
            return
        self.conn.execute(
            """
            INSERT INTO capture_corrections (raw_text, clean_text, predicted_kind, corrected_kind)
            VALUES (?, ?, ?, ?)
            """,
            (raw, clean, predicted, corrected),
        )
        self.conn.commit()

    def correction_examples(self, limit: int = 1000) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            """
            SELECT clean_text, corrected_kind FROM capture_corrections
            WHERE clean_text != '' AND corrected_kind IN ('task', 'goal', 'note')
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [(row["clean_text"], row["corrected_kind"]) for row in rows]

    def send_to_inbox(self, intent: CaptureIntent, confidence: float, source: str) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO capture_inbox (
                raw_text, clean_text, suggested_kind, day, planned_time, confidence, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intent.raw,
                intent.text,
                intent.kind,
                date_key(intent.day),
                intent.planned_time,
                confidence,
                source,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def inbox_items(self, limit: int = 20):
        return self.conn.execute(
            """
            SELECT * FROM capture_inbox
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def remove_inbox_item(self, inbox_id: int) -> None:
        self.conn.execute("DELETE FROM capture_inbox WHERE id = ?", (inbox_id,))
        self.conn.commit()

    def related(self, query: str, limit: int = 8) -> list[MemoryItem]:
        terms = _query_terms(query)
        items = self._structured_context(terms, limit)
        if self._fts_available and terms:
            items.extend(self._fts_context(terms, limit))
        elif terms:
            items.extend(self._like_context(terms, limit))
        return _dedupe(items)[:limit]

    def training_examples(self, limit: int = 300) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            """
            SELECT clean_text, kind FROM capture_events
            WHERE clean_text != '' AND kind != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        examples = self.correction_examples(limit)
        examples.extend((row["clean_text"], row["kind"]) for row in rows)
        return examples[:limit]

    def _structured_context(self, terms: list[str], limit: int) -> list[MemoryItem]:
        if not terms:
            return []
        like = [f"%{term}%" for term in terms[:4]]
        clauses = " OR ".join(["title LIKE ?"] * len(like))
        items: list[MemoryItem] = []
        for row in self.conn.execute(
            f"""
            SELECT title, created_on AS day FROM goals
            WHERE archived_on IS NULL AND ({clauses})
            ORDER BY sort_order ASC, id DESC
            LIMIT ?
            """,
            [*like, limit],
        ).fetchall():
            items.append(MemoryItem("goal", row["title"], parse_day(row["day"]), "active goal", 0.9))
        for row in self.conn.execute(
            f"""
            SELECT title, day, planned_time FROM daily_tasks
            WHERE status != 'archived' AND ({clauses})
            ORDER BY day DESC, id DESC
            LIMIT ?
            """,
            [*like, limit],
        ).fetchall():
            context = f"task {row['planned_time']}".strip()
            items.append(MemoryItem("task", row["title"], parse_day(row["day"]), context, 0.8))
        return items

    def _fts_context(self, terms: list[str], limit: int) -> list[MemoryItem]:
        query = " OR ".join(term.replace('"', "") for term in terms)
        try:
            rows = self.conn.execute(
                """
                SELECT e.kind, e.clean_text, e.day, e.context, bm25(capture_fts) AS rank
                FROM capture_fts
                JOIN capture_events e ON e.id = capture_fts.rowid
                WHERE capture_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        except OperationalError:
            return []
        return [
            MemoryItem(row["kind"], row["clean_text"], parse_day(row["day"]), row["context"], 0.7)
            for row in rows
        ]

    def _like_context(self, terms: list[str], limit: int) -> list[MemoryItem]:
        like = [f"%{term}%" for term in terms[:4]]
        clauses = " OR ".join(["clean_text LIKE ?"] * len(like))
        rows = self.conn.execute(
            f"""
            SELECT kind, clean_text, day, context FROM capture_events
            WHERE {clauses}
            ORDER BY id DESC
            LIMIT ?
            """,
            [*like, limit],
        ).fetchall()
        return [
            MemoryItem(row["kind"], row["clean_text"], parse_day(row["day"]), row["context"], 0.6)
            for row in rows
        ]

    def _has_fts(self) -> bool:
        try:
            self.conn.execute("SELECT rowid FROM capture_fts LIMIT 1")
            return True
        except OperationalError:
            return False


def recent_days_context(day: date | None = None) -> str:
    current = day or today()
    return f"window:{date_key(current - timedelta(days=7))}..{date_key(current)}"


def _query_terms(value: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "today", "tomorrow"}
    terms = []
    for raw in value.lower().replace(":", " ").replace("-", " ").split():
        term = "".join(ch for ch in raw if ch.isalnum())
        if len(term) >= 3 and term not in stop:
            terms.append(term)
    return terms[:8]


def _dedupe(items: list[MemoryItem]) -> list[MemoryItem]:
    seen = set()
    result = []
    for item in sorted(items, key=lambda candidate: candidate.score, reverse=True):
        key = (item.kind, item.text.lower(), item.day)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
