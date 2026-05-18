from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


LABELS = ("task", "goal", "note")


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.base_cache))
    usage = read_jsonl(Path(args.usage))
    additions = []
    for row in usage:
        label = normalize_label(row.get("label", ""))
        text = " ".join(str(row.get("text", "")).split())
        if label and text:
            repeat = args.correction_repeats if row.get("source") == "correction" else 1
            for _ in range(repeat):
                additions.append(
                    {
                        "text": text,
                        "label": label,
                        "source": "personal",
                        "teacher_logits": one_hot_logits(label),
                        "real_usage_source": row.get("source", "usage"),
                    }
                )
    merged = dedupe(rows + additions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in merged:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Base rows: {len(rows)}")
    print(f"Usage rows added before dedupe: {len(additions)}")
    print(f"Merged rows: {len(merged)} -> {output}")
    print("Labels:", dict(Counter(row["label"] for row in merged)))
    print("Sources:", dict(Counter(row.get("source", "base") for row in merged)))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Bad JSON at {path}:{line_number}") from exc
    return rows


def normalize_label(value: str) -> str:
    label = value.strip().lower()
    if label == "plan":
        label = "note"
    return label if label in LABELS else ""


def one_hot_logits(label: str) -> list[float]:
    return [4.0 if candidate == label else -2.0 for candidate in LABELS]


def dedupe(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        label = normalize_label(str(row.get("label", "")))
        text = " ".join(str(row.get("text", "")).split())
        if not text or not label:
            continue
        key = (text.lower(), label)
        if key in seen:
            continue
        seen.add(key)
        clean = dict(row)
        clean["text"] = text
        clean["label"] = label
        if "teacher_logits" not in clean:
            clean["teacher_logits"] = one_hot_logits(label)
        result.append(clean)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge real Momentum usage into the 3-class distillation cache.")
    parser.add_argument("--base-cache", default="experiments/three_class/cache/three_class_cache.jsonl")
    parser.add_argument("--usage", default="training_data/real_usage/momentum_real_usage.jsonl")
    parser.add_argument("--output", default="experiments/three_class/cache/three_class_with_real_usage.jsonl")
    parser.add_argument("--correction-repeats", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    main()
