from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from momentum.core.dates import today


INTENTS = {"task", "goal", "note"}
TIME_RE = re.compile(r"\b(?:at\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)\b", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?\b")


@dataclass(slots=True)
class CaptureIntent:
    kind: str
    text: str
    day: date
    planned_time: str = ""
    carry_forward: bool = False
    raw: str = ""

    @property
    def label(self) -> str:
        when = "today" if self.day == today() else self.day.isoformat()
        clock = f" at {self.planned_time}" if self.planned_time else ""
        return f"{self.kind.title()} saved for {when}{clock}"


def parse_capture(value: str, base_day: date | None = None) -> CaptureIntent | None:
    raw = value.strip()
    if not raw:
        return None
    day = base_day or today()
    working = raw
    explicit_kind, working = _explicit_kind(working)
    day, working = _extract_day(working, day)
    planned_time, working = _extract_time(working)
    carry_forward, working = _extract_carry(working)
    kind = explicit_kind or _infer_kind(working, bool(planned_time), day != (base_day or today()))
    text = _clean_text(working)
    if not text:
        return None
    return CaptureIntent(
        kind=kind,
        text=text,
        day=day,
        planned_time=planned_time,
        carry_forward=carry_forward,
        raw=raw,
    )


def _explicit_kind(value: str) -> tuple[str | None, str]:
    match = re.match(r"^\s*(task|todo|goal|habit|note|notes|plan)\s*[:\-]\s*(.+)$", value, re.IGNORECASE)
    if not match:
        return None, value
    raw_kind = match.group(1).lower()
    kind = {
        "todo": "task",
        "habit": "goal",
        "notes": "note",
        "plan": "note",
    }.get(raw_kind, raw_kind)
    return kind, match.group(2)


def _extract_day(value: str, fallback: date) -> tuple[date, str]:
    lowered = value.lower()
    replacements = [
        ("day after tomorrow", fallback + timedelta(days=2)),
        ("tomorrow", fallback + timedelta(days=1)),
        ("today", fallback),
        ("yesterday", fallback - timedelta(days=1)),
    ]
    for phrase, day in replacements:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return day, re.sub(rf"\b{re.escape(phrase)}\b", "", value, flags=re.IGNORECASE).strip()

    match = ISO_DATE_RE.search(value)
    if match:
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed:
            return parsed, (value[: match.start()] + value[match.end() :]).strip()

    match = SLASH_DATE_RE.search(value)
    if match:
        year = int(match.group(3)) if match.group(3) else fallback.year
        parsed = _safe_date(year, int(match.group(1)), int(match.group(2)))
        if parsed:
            return parsed, (value[: match.start()] + value[match.end() :]).strip()

    weekday = _weekday_date(value, fallback)
    if weekday:
        day, start, end = weekday
        return day, (value[:start] + value[end:]).strip()
    return fallback, value


def _extract_time(value: str) -> tuple[str, str]:
    match = TIME_RE.search(value)
    if not match:
        return "", value
    hour = int(match.group(1))
    minute = int(match.group(2))
    clean = (value[: match.start()] + value[match.end() :]).strip()
    return f"{hour:02d}:{minute:02d}", clean


def _extract_carry(value: str) -> tuple[bool, str]:
    patterns = [
        r"\bcarry\s+forward\b",
        r"\bcarry\b",
        r"\broll\s+over\b",
    ]
    changed = value
    carry = False
    for pattern in patterns:
        if re.search(pattern, changed, re.IGNORECASE):
            carry = True
            changed = re.sub(pattern, "", changed, flags=re.IGNORECASE)
    return carry, changed.strip()


def _infer_kind(value: str, has_time: bool, has_future_day: bool) -> str:
    lowered = value.lower().strip()
    if lowered.startswith(("remember ", "note ", "notes ", "journal ", "felt ", "feeling ")):
        return "note"
    if lowered.startswith(("plan ", "strategy ", "roadmap ", "outline ")):
        return "note"
    if lowered.startswith(("schedule ", "prepare for ")):
        return "task"
    if lowered.startswith(("goal ", "habit ", "daily ", "every day ", "build habit ")):
        return "goal"
    if has_time or has_future_day:
        return "task"
    if any(word in lowered for word in ("finish ", "send ", "call ", "email ", "buy ", "fix ", "review ", "submit ", "apply ")):
        return "task"
    return "note"


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" -:")
    for prefix in ("task ", "todo ", "goal ", "habit ", "note ", "notes ", "plan "):
        if text.lower().startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _weekday_date(value: str, fallback: date) -> tuple[date, int, int] | None:
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for index, name in enumerate(names):
        match = re.search(rf"\b(next\s+)?{name}\b", value, re.IGNORECASE)
        if not match:
            continue
        days = (index - fallback.weekday()) % 7
        if days == 0:
            days += 7
        return fallback + timedelta(days=days), match.start(), match.end()
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
