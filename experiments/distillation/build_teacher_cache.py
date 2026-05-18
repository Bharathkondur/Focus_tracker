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
            "row": row,
            "input_ids": encoded["input_ids"].squeeze(0),
            "attention_mask": encoded["attention_mask"].squeeze(0),
        }


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_rows(Path(args.dataset), source="base")
    rows.extend(load_rows(Path(args.personal_dataset), source="personal"))
    rows = dedupe(rows)

    device = select_device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(args.teacher)
    teacher = AutoModelForSequenceClassification.from_pretrained(args.teacher).to(device)
    teacher.eval()

    loader = DataLoader(
        TextDataset(rows, tokenizer, args.max_length),
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate,
        num_workers=0,
    )

    id_to_label = {int(key): value for key, value in teacher.config.id2label.items()}
    written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        with torch.inference_mode():
            for batch in loader:
                model_inputs = {
                    "input_ids": batch["input_ids"].to(device),
                    "attention_mask": batch["attention_mask"].to(device),
                }
                logits = teacher(**model_inputs).logits.float().cpu()
                probabilities = torch.softmax(logits, dim=-1)
                for row, logit, probs in zip(batch["rows"], logits, probabilities):
                    teacher_probs = {
                        id_to_label[index]: round(float(probs[index].item()), 8)
                        for index in range(len(LABELS))
                    }
                    output = {
                        "text": row["text"],
                        "label": row["label"],
                        "source": row["source"],
                        "teacher_probs": teacher_probs,
                        "teacher_logits": [round(float(value), 8) for value in logit.tolist()],
                    }
                    handle.write(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n")
                    written += 1
    print(f"Wrote {written} rows to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache ModernBERT teacher logits for student distillation.")
    parser.add_argument("--dataset", default="training_data/final/momentum_intent_20k_balanced.jsonl")
    parser.add_argument("--personal-dataset", default="training_data/final/personal_corrections_2k.jsonl")
    parser.add_argument("--teacher", default="experiments/modernbert/latest")
    parser.add_argument("--output", default="experiments/distillation/cache/teacher_modernbert_cache.jsonl")
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


def dedupe(rows: list[dict]) -> list[dict]:
    positions = {}
    deduped = []
    for row in rows:
        key = (row["text"].lower(), row["label"])
        if key in positions:
            if row.get("source") == "personal":
                deduped[positions[key]] = row
            continue
        positions[key] = len(deduped)
        deduped.append(row)
    return deduped


def collate(items: list[dict]) -> dict:
    return {
        "rows": [item["row"] for item in items],
        "input_ids": torch.stack([item["input_ids"] for item in items]),
        "attention_mask": torch.stack([item["attention_mask"] for item in items]),
    }


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
