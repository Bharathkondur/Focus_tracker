from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


SOURCE = Path("experiments/distillation_v2/cache/ensemble_teacher_cache.jsonl")
OUTPUT = Path("experiments/three_class/cache/three_class_cache.jsonl")
LABELS = ("task", "goal", "note")


def main() -> None:
    rows = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        label = "note" if row["label"] == "plan" else row["label"]
        probs4 = row["teacher_probs"]
        probs3 = {
            "task": probs4.get("task", 0.0),
            "goal": probs4.get("goal", 0.0),
            "note": probs4.get("note", 0.0) + probs4.get("plan", 0.0),
        }
        total = sum(probs3.values())
        probs3 = {key: value / total for key, value in probs3.items()}
        rows.append(
            {
                "text": row["text"],
                "label": label,
                "source": row["source"],
                "teacher_probs": probs3,
                "teacher_logits": [round(math.log(max(probs3[label], 1e-8)), 8) for label in LABELS],
            }
        )

    rows = balanced(rows, per_label=6000)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )
    print("Wrote", len(rows), OUTPUT)
    print("Labels:", dict(Counter(row["label"] for row in rows)))
    print("Sources:", dict(Counter(row["source"] for row in rows)))


def balanced(rows: list[dict], per_label: int) -> list[dict]:
    rng = random.Random(42)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row["label"]].append(row)
    selected = []
    for label in LABELS:
        values = buckets[label]
        rng.shuffle(values)
        selected.extend(values[:per_label])
    rng.shuffle(selected)
    return selected


if __name__ == "__main__":
    main()
