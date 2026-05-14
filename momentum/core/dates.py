from __future__ import annotations

from datetime import date, datetime, timedelta


def today() -> date:
    return date.today()


def date_key(day: date) -> str:
    return day.isoformat()


def parse_day(value: str) -> date:
    return date.fromisoformat(value)


def clamp_to_today(day: date) -> date:
    current = today()
    return day if day <= current else current


def greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 18:
        return "Good Afternoon"
    return "Good Evening"


def friendly_day(day: date) -> str:
    current = today()
    if day == current:
        return "Today"
    if day == current - timedelta(days=1):
        return "Yesterday"
    return day.strftime("%a, %b %d, %Y")


def header_day(day: date) -> str:
    try:
        return day.strftime("%A - %B %-d").upper()
    except ValueError:
        return day.strftime("%A - %B %#d").upper()


def days_back(count: int, end: date | None = None) -> list[date]:
    last = end or today()
    return [last - timedelta(days=offset) for offset in range(count - 1, -1, -1)]
