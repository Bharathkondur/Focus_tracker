from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from momentum.data.paths import DB_PATH


LABELS = {"task", "goal", "note"}


def main() -> None:
    args = parse_args()
    rows = export_rows(Path(args.db), args.include_captures, args.min_confidence)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} rows to {output}")
    print("Labels:", dict(Counter(row["label"] for row in rows)))
    print("Sources:", dict(Counter(row["source"] for row in rows)))


def export_rows(db_path: Path, include_captures: bool, min_confidence: float) -> list[dict[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, str]] = []
    try:
        for row in conn.execute(
            """
            SELECT clean_text, corrected_kind, predicted_kind, created_at
            FROM capture_corrections
            WHERE clean_text != ''
            ORDER BY id ASC
            """
        ).fetchall():
            label = normalize_label(row["corrected_kind"])
            if label:
                rows.append(
                    {
                        "text": row["clean_text"].strip(),
                        "label": label,
                        "source": "correction",
                        "predicted": normalize_label(row["predicted_kind"]) or row["predicted_kind"],
                        "created_at": row["created_at"],
                    }
                )
        if include_captures:
            for row in conn.execute(
                """
                SELECT clean_text, kind, confidence, source, created_at
                FROM capture_events
                WHERE clean_text != '' AND confidence >= ?
                ORDER BY id ASC
                """,
                (min_confidence,),
            ).fetchall():
                label = normalize_label(row["kind"])
                if label:
                    rows.append(
                        {
                            "text": row["clean_text"].strip(),
                            "label": label,
                            "source": f"capture:{row['source']}",
                            "confidence": round(float(row["confidence"]), 4),
                            "created_at": row["created_at"],
                        }
                    )
    finally:
        conn.close()
    return dedupe(rows)


def normalize_label(value: str) -> str:
    label = (value or "").strip().lower()
    if label == "plan":
        label = "note"
    return label if label in LABELS else ""


def dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        key = (" ".join(row["text"].lower().split()), row["label"])
        if not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export real Momentum usage as 3-class intent data.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default="training_data/real_usage/momentum_real_usage.jsonl")
    parser.add_argument("--include-captures", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-confidence", type=float, default=0.9)
    return parser.parse_args()


if __name__ == "__main__":
    main()
