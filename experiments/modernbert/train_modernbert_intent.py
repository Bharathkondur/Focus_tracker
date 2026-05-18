from __future__ import annotations

import argparse
import json
import random
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_cosine_schedule_with_warmup


LABELS = ("task", "goal", "note", "plan")


class IntentDataset(Dataset):
    def __init__(self, rows: list[dict[str, str]], tokenizer, label_to_id: dict[str, int], max_length: int):
        self.rows = rows
        self.tokenizer = tokenizer
        self.label_to_id = label_to_id
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.rows[index]
        encoded = self.tokenizer(
            row["text"],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        item = {key: value.squeeze(0) for key, value in encoded.items()}
        item["labels"] = torch.tensor(self.label_to_id[row["label"]], dtype=torch.long)
        return item


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    dataset_path = Path(args.dataset)
    run_name = args.run_name or time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / run_name
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(dataset_path)
    if args.limit:
        rows = balanced_limit(rows, args.limit, args.seed)
    train_rows, val_rows, test_rows = stratified_split(rows, args.val_split, args.test_split, args.seed)

    label_to_id = {label: index for index, label in enumerate(LABELS)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    device = select_device(args.device)
    use_amp = args.amp and device.type == "cuda"

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=args.trust_remote_code)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=len(LABELS),
        label2id=label_to_id,
        id2label=id_to_label,
        ignore_mismatched_sizes=True,
        trust_remote_code=args.trust_remote_code,
    ).to(device)

    train_loader = DataLoader(
        IntentDataset(train_rows, tokenizer, label_to_id, args.max_length),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        IntentDataset(val_rows, tokenizer, label_to_id, args.max_length),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=0,
    )
    test_loader = DataLoader(
        IntentDataset(test_rows, tokenizer, label_to_id, args.max_length),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=0,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = get_cosine_schedule_with_warmup(optimizer, warmup_steps, total_steps)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    metadata = {
        "dataset": str(dataset_path),
        "base_model": args.base_model,
        "rows": {"total": len(rows), "train": len(train_rows), "val": len(val_rows), "test": len(test_rows)},
        "labels": LABELS,
        "label_to_id": label_to_id,
        "max_length": args.max_length,
        "parameters": count_parameters(model),
        "device": str(device),
        "use_amp": use_amp,
        "args": vars(args),
    }
    write_json(output_dir / "training_metadata.json", metadata)

    print(f"Dataset: {dataset_path}")
    print(f"Base model: {args.base_model}")
    print(f"Rows: train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")
    print(f"Labels: {dict(Counter(row['label'] for row in rows))}")
    print(f"Device: {device} amp={use_amp}")
    print(f"Parameters: {metadata['parameters']:,}")

    best_macro_f1 = -1.0
    best_epoch = 0
    history = []
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(
            model,
            train_loader,
            optimizer,
            scheduler,
            scaler,
            device,
            use_amp,
            args.grad_clip,
        )
        val_metrics = evaluate(model, val_loader, device)
        history.append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_metrics["loss"],
                "val_accuracy": val_metrics["accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
            }
        )
        print(
            f"epoch {epoch:02d} "
            f"train_loss={train_loss:.4f} "
            f"val_loss={val_metrics['loss']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} "
            f"val_macro_f1={val_metrics['macro_f1']:.4f}"
        )
        if val_metrics["macro_f1"] > best_macro_f1:
            best_macro_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)

    best_model = AutoModelForSequenceClassification.from_pretrained(
        output_dir,
        trust_remote_code=args.trust_remote_code,
    ).to(device)
    val_metrics = evaluate(best_model, val_loader, device)
    test_metrics = evaluate(best_model, test_loader, device)
    metrics = {
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_macro_f1,
        "val": val_metrics,
        "test": test_metrics,
        "history": history,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    write_json(output_dir / "metrics.json", metrics)

    latest_dir = output_dir.parent.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(output_dir, latest_dir)

    print("Saved:", output_dir)
    print("Latest:", latest_dir)
    print(f"Test accuracy={test_metrics['accuracy']:.4f} macro_f1={test_metrics['macro_f1']:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a ModernBERT challenger for Momentum intent classification.")
    parser.add_argument("--dataset", default="training_data/final/momentum_intent_20k_balanced.jsonl")
    parser.add_argument("--output-dir", default="experiments/modernbert/runs")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--base-model", default="answerdotai/ModernBERT-base")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.08)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--max-length", type=int, default=64)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--limit", type=int, default=0, help="Optional balanced row limit for smoke tests.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    rows = []
    seen = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        text = " ".join(str(row.get("text", "")).strip().split())
        label = row.get("label")
        if label not in LABELS or not text:
            raise ValueError(f"Bad row at {path}:{line_number}")
        key = (text.lower(), label)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"text": text, "label": label})
    return rows


def balanced_limit(rows: list[dict[str, str]], limit: int, seed: int) -> list[dict[str, str]]:
    if limit <= 0 or limit >= len(rows):
        return rows
    rng = random.Random(seed)
    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row)
    per_label = max(1, limit // len(LABELS))
    selected = []
    for label in LABELS:
        label_rows = by_label[label][:]
        rng.shuffle(label_rows)
        selected.extend(label_rows[:per_label])
    rng.shuffle(selected)
    return selected


def stratified_split(
    rows: list[dict[str, str]],
    val_split: float,
    test_split: float,
    seed: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row)
    rng = random.Random(seed)
    train_rows: list[dict[str, str]] = []
    val_rows: list[dict[str, str]] = []
    test_rows: list[dict[str, str]] = []
    for label in LABELS:
        label_rows = by_label[label]
        rng.shuffle(label_rows)
        val_count = int(len(label_rows) * val_split)
        test_count = int(len(label_rows) * test_split)
        val_rows.extend(label_rows[:val_count])
        test_rows.extend(label_rows[val_count : val_count + test_count])
        train_rows.extend(label_rows[val_count + test_count :])
    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    rng.shuffle(test_rows)
    return train_rows, val_rows, test_rows


def select_device(choice: str) -> torch.device:
    if choice == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but this Python environment has CPU-only PyTorch.")
        return torch.device("cuda")
    if choice == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def train_one_epoch(
    model,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler,
    scaler: torch.amp.GradScaler,
    device: torch.device,
    use_amp: bool,
    grad_clip: float,
) -> float:
    model.train()
    total_loss = 0.0
    total = 0
    for batch in loader:
        batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            output = model(**batch)
            loss = output.loss
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        if grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()
        batch_size = batch["labels"].size(0)
        total_loss += float(loss.item()) * batch_size
        total += batch_size
    return total_loss / max(1, total)


@torch.inference_mode()
def evaluate(model, loader: DataLoader, device: torch.device) -> dict:
    model.eval()
    total_loss = 0.0
    total = 0
    predictions = []
    targets = []
    for batch in loader:
        batch = {key: value.to(device, non_blocking=True) for key, value in batch.items()}
        output = model(**batch)
        logits = output.logits
        pred = torch.argmax(logits, dim=-1)
        batch_size = batch["labels"].size(0)
        total_loss += float(output.loss.item()) * batch_size
        total += batch_size
        predictions.extend(int(value) for value in pred.cpu().tolist())
        targets.extend(int(value) for value in batch["labels"].cpu().tolist())
    report = classification_report(
        targets,
        predictions,
        target_names=LABELS,
        output_dict=True,
        zero_division=0,
    )
    return {
        "loss": total_loss / max(1, total),
        "accuracy": accuracy_score(targets, predictions),
        "macro_f1": f1_score(targets, predictions, average="macro"),
        "per_label": {label: report[label] for label in LABELS},
        "confusion_matrix": confusion_matrix(targets, predictions).tolist(),
    }


def count_parameters(model) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True


if __name__ == "__main__":
    main()
