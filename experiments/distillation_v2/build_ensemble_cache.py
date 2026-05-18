from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer


LABELS = ("task", "goal", "note", "plan")


class TextDataset(Dataset):
    def __init__(self, rows: list[dict], tokenizer, max_length: int):
        self.rows = rows
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict:
        row = self.rows[index]
        encoded = self.tokenizer(
            row["text"],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        return {
            "index": index,
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
        }


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    rows.extend(load_rows(Path(args.dataset), "base"))
    rows.extend(load_rows(Path(args.hard_dataset), "hard"))
    rows.extend(load_rows(Path(args.personal_dataset), "personal"))
    rows = dedupe_with_extra_sources(rows)

    device = select_device(args.device)
    modern_probs = teacher_probs(rows, args.modernbert_teacher, args.batch_size, args.max_length, device)
    minilm_probs = teacher_probs(rows, args.minilm_teacher, args.batch_size, args.max_length, device)

    with output_path.open("w", encoding="utf-8") as handle:
        for row, modern, minilm in zip(rows, modern_probs, minilm_probs):
            ensemble = [(modern[i] + minilm[i]) / 2 for i in range(len(LABELS))]
            total = sum(ensemble)
            ensemble = [value / total for value in ensemble]
            output = {
                "text": row["text"],
                "label": row["label"],
                "source": row["source"],
                "modernbert_probs": {LABELS[i]: round(modern[i], 8) for i in range(len(LABELS))},
                "minilm_probs": {LABELS[i]: round(minilm[i], 8) for i in range(len(LABELS))},
                "teacher_probs": {LABELS[i]: round(ensemble[i], 8) for i in range(len(LABELS))},
                "teacher_logits": [round(float(torch.log(torch.tensor(max(value, 1e-8))).item()), 8) for value in ensemble],
            }
            handle.write(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(f"Wrote {len(rows)} rows to {output_path}")
    print("Sources:", source_counts(rows))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an ensemble teacher cache from ModernBERT and MiniLM.")
    parser.add_argument("--dataset", default="training_data/final/momentum_intent_20k_balanced.jsonl")
    parser.add_argument("--hard-dataset", default="training_data/final/hard_ambiguous_2k.jsonl")
    parser.add_argument("--personal-dataset", default="training_data/final/personal_corrections_2k.jsonl")
    parser.add_argument("--modernbert-teacher", default="experiments/modernbert/latest")
    parser.add_argument("--minilm-teacher", default="models/momentum_intent/premium_latest")
    parser.add_argument("--output", default="experiments/distillation_v2/cache/ensemble_teacher_cache.jsonl")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=48)
    return parser.parse_args()


def load_rows(path: Path, source: str) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        text = " ".join(str(obj.get("text", "")).strip().split())
        label = obj.get("label")
        if label not in LABELS or not text:
            raise ValueError(f"Bad row at {path}:{line_number}")
        rows.append({"text": text, "label": label, "source": source})
    return rows


def dedupe_with_extra_sources(rows: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for row in rows:
        key = (row["text"].lower(), row["label"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


@torch.inference_mode()
def teacher_probs(rows: list[dict], model_dir: str, batch_size: int, max_length: int, device: torch.device) -> list[list[float]]:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device)
    model.eval()
    id_to_label = {int(key): value for key, value in model.config.id2label.items()}
    label_to_teacher_id = {label: index for index, label in id_to_label.items()}
    loader = DataLoader(
        TextDataset(rows, tokenizer, max_length),
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate,
        num_workers=0,
    )
    result = [None] * len(rows)
    for batch in loader:
        model_inputs = {
            "input_ids": batch["input_ids"].to(device),
            "attention_mask": batch["attention_mask"].to(device),
        }
        probabilities = torch.softmax(model(**model_inputs).logits.float().cpu(), dim=-1)
        for row_index, probs in zip(batch["indexes"], probabilities):
            ordered = [float(probs[label_to_teacher_id[label]].item()) for label in LABELS]
            result[row_index] = ordered
    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def collate(items: list[dict]) -> dict:
    return {
        "indexes": [item["index"] for item in items],
        "input_ids": torch.stack([item["input_ids"] for item in items]),
        "attention_mask": torch.stack([item["attention_mask"] for item in items]),
    }


def source_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    return counts


def select_device(choice: str) -> torch.device:
    if choice == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but CUDA is not available.")
        return torch.device("cuda")
    if choice == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


if __name__ == "__main__":
    main()
