from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path

from momentum.capture.intent import CaptureIntent
from momentum.core.dates import date_key
from momentum.data.paths import BASE_DIR
from momentum.data.repository import Repository


CAPTURE_DIR = BASE_DIR / "momentum_captures"


def folder_for(intent: CaptureIntent) -> Path:
    return CAPTURE_DIR / f"{intent.day:%Y}" / f"{intent.day:%m-%B}" / f"{intent.day:%d}"


def append_capture(intent: CaptureIntent) -> Path:
    folder = folder_for(intent)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{intent.kind}s.md"
    stamp = datetime.now().strftime("%H:%M")
    planned = f" @{intent.planned_time}" if intent.planned_time else ""
    carry = " [carry]" if intent.carry_forward else ""
    line = f"- {stamp}{planned}{carry} {intent.text}\n"
    if not path.exists():
        title = f"# {intent.kind.title()}s - {date_key(intent.day)}\n\n"
        path.write_text(title, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return path


def export_weekly_summary(repo: Repository) -> Path:
    from momentum.capture.summary import build_summary
    from momentum.core.dates import today

    end = today()
    start = end - timedelta(days=6)
    summary = build_summary(repo, start, end)
    folder = CAPTURE_DIR / f"{end:%Y}" / f"{end:%m-%B}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"week-{end.isocalendar().week:02d}-summary.md"
    lines = [
        f"# Momentum Weekly Summary - {date_key(start)} to {date_key(end)}",
        "",
        "## Metrics",
        "",
    ]
    for metric in summary.metrics:
        detail = f" - {metric.detail}" if metric.detail else ""
        lines.append(f"- **{metric.label}:** {metric.value}{detail}")
    lines.extend(["", "## What Happened", ""])
    lines.extend(f"- {item}" for item in summary.bullets)
    lines.extend(["", "## Suggested Focus", ""])
    lines.extend(f"- {item}" for item in summary.focus)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
