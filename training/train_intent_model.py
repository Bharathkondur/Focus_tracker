from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from momentum_intent_model import (
    LABELS,
    IntentDataset,
    ModelConfig,
    MomentumIntentEncoder,
    build_vocab,
    config_to_dict,
    count_parameters,
    save_json,
)


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(dataset_path)
    train_rows, val_rows, test_rows = stratified_split(rows, args.val_split, args.test_split, args.seed)

    vocab = build_vocab((row["text"] for row in train_rows), args.vocab_size)
    token_to_id = {token: index for index, token in enumerate(vocab)}
    label_to_id = {label: index for index, label in enumerate(LABELS)}
    id_to_label = {index: label for label, index in label_to_id.items()}

    config = ModelConfig(
        vocab_size=len(vocab),
        max_length=args.max_length,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        num_heads=args.num_heads,
        intermediate_size=args.intermediate_size,
        dropout=args.dropout,
    )

    device = select_device(args.device)
    use_amp = args.amp and device.type == "cuda"
    train_dataset = IntentDataset(train_rows, token_to_id, label_to_id, config.max_length)
    val_dataset = IntentDataset(val_rows, token_to_id, label_to_id, config.max_length)
    test_dataset = IntentDataset(test_rows, token_to_id, label_to_id, config.max_length)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.eval_batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=args.eval_batch_size, shuffle=False, num_workers=0)

    model = MomentumIntentEncoder(config, len(LABELS)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda step: lr_schedule(step, warmup_steps, total_steps),
    )
    loss_fn = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    metadata = {
        "dataset": str(dataset_path),
        "rows": {
            "total": len(rows),
            "train": len(train_rows),
            "val": len(val_rows),
            "test": len(test_rows),
        },
        "labels": LABELS,
        "model_config": config_to_dict(config),
        "parameters": count_parameters(model),
        "device": str(device),
        "use_amp": use_amp,
        "args": vars(args),
    }
    save_json(output_dir / "training_metadata.json", metadata)
    save_json(output_dir / "vocab.json", vocab)
    save_json(output_dir / "label_to_id.json", label_to_id)

    print(f"Dataset: {dataset_path}")
    print(f"Rows: train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")
    print(f"Labels: {dict(Counter(row['label'] for row in rows))}")
    print(f"Device: {device} amp={use_amp}")
    print(f"Parameters: {metadata['parameters']:,}")

    best_metric = -1.0
    best_epoch = 0
    history = []
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(
            model,
            train_loader,
            optimizer,
            scheduler,
            loss_fn,
            scaler,
            device,
            use_amp,
            args.grad_clip,
        )
        val_metrics = evaluate(model, val_loader, loss_fn, device)
        row = {"epoch": epoch, "train_loss": train_loss, **prefix_keys(val_metrics, "val_")}
        history.append(row)
        print(
            f"epoch {epoch:02d} "
            f"train_loss={train_loss:.4f} "
            f"val_loss={val_metrics['loss']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} "
            f"val_macro_f1={val_metrics['macro_f1']:.4f}"
        )
        if val_metrics["macro_f1"] > best_metric:
            best_metric = val_metrics["macro_f1"]
            best_epoch = epoch
            save_checkpoint(output_dir / "model.pt", model, token_to_id, label_to_id, id_to_label, config, metadata)

    model, token_to_id, id_to_label, config, checkpoint = load_best(output_dir / "model.pt", device)
    final_loss = nn.CrossEntropyLoss()
    val_metrics = evaluate(model, val_loader, final_loss, device)
    test_metrics = evaluate(model, test_loader, final_loss, device)
    result = {
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_metric,
        "val": val_metrics,
        "test": test_metrics,
        "history": history,
        "elapsed_seconds": round(time.time() - started, 2),
        "checkpoint_parameters": checkpoint["parameters"],
    }
    save_json(output_dir / "metrics.json", result)
    save_json(output_dir / "model_config.json", config_to_dict(config))

    latest_dir = output_dir.parent / "latest"
    if latest_dir.resolve() != output_dir.resolve():
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(output_dir, latest_dir)

    print("Saved:", output_dir / "model.pt")
    print("Latest:", latest_dir)
    print(f"Test accuracy={test_metrics['accuracy']:.4f} macro_f1={test_metrics['macro_f1']:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the local Momentum intent encoder.")
    parser.add_argument(
        "--dataset",
        default="training_data/final/momentum_intent_20k_balanced.jsonl",
        help="JSONL file with text and label fields.",
    )
    parser.add_argument("--output-dir", default="models/momentum_intent/run")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--eval-batch-size", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.08)
    parser.add_argument("--label-smoothing", type=float, default=0.03)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--vocab-size", type=int, default=10000)
    parser.add_argument("--max-length", type=int, default=40)
    parser.add_argument("--hidden-size", type=int, default=192)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-heads", type=int, default=6)
    parser.add_argument("--intermediate-size", type=int, default=768)
    parser.add_argument("--dropout", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
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
    if not rows:
        raise ValueError(f"No rows found in {path}")
    return rows


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


def lr_schedule(step: int, warmup_steps: int, total_steps: int) -> float:
    if step < warmup_steps:
        return max(0.05, step / max(1, warmup_steps))
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    return max(0.05, 0.5 * (1.0 + math.cos(math.pi * progress)))


def train_one_epoch(
    model: MomentumIntentEncoder,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LRScheduler,
    loss_fn: nn.Module,
    scaler: torch.amp.GradScaler,
    device: torch.device,
    use_amp: bool,
    grad_clip: float,
) -> float:
    model.train()
    total_loss = 0.0
    total = 0
    for batch in loader:
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attention_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            logits = model(input_ids, attention_mask)
            loss = loss_fn(logits, labels)
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        if grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()

        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        total += batch_size
    return total_loss / max(1, total)


@torch.inference_mode()
def evaluate(
    model: MomentumIntentEncoder,
    loader: DataLoader,
    loss_fn: nn.Module,
    device: torch.device,
) -> dict:
    model.eval()
    total_loss = 0.0
    total = 0
    correct = 0
    predictions: list[int] = []
    gold: list[int] = []
    for batch in loader:
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attention_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        logits = model(input_ids, attention_mask)
        loss = loss_fn(logits, labels)
        predicted = torch.argmax(logits, dim=-1)
        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        total += batch_size
        correct += int((predicted == labels).sum().item())
        predictions.extend(int(value) for value in predicted.cpu().tolist())
        gold.extend(int(value) for value in labels.cpu().tolist())
    return {
        "loss": total_loss / max(1, total),
        "accuracy": correct / max(1, total),
        "macro_f1": macro_f1(predictions, gold, len(LABELS)),
        "confusion_matrix": confusion_matrix(predictions, gold, len(LABELS)),
    }


def macro_f1(predictions: list[int], gold: list[int], num_labels: int) -> float:
    scores = []
    for label in range(num_labels):
        tp = sum(1 for pred, target in zip(predictions, gold) if pred == label and target == label)
        fp = sum(1 for pred, target in zip(predictions, gold) if pred == label and target != label)
        fn = sum(1 for pred, target in zip(predictions, gold) if pred != label and target == label)
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        scores.append(2 * precision * recall / max(1e-9, precision + recall))
    return sum(scores) / len(scores)


def confusion_matrix(predictions: list[int], gold: list[int], num_labels: int) -> list[list[int]]:
    matrix = [[0 for _ in range(num_labels)] for _ in range(num_labels)]
    for pred, target in zip(predictions, gold):
        matrix[target][pred] += 1
    return matrix


def save_checkpoint(
    path: Path,
    model: MomentumIntentEncoder,
    token_to_id: dict[str, int],
    label_to_id: dict[str, int],
    id_to_label: dict[int, str],
    config: ModelConfig,
    metadata: dict,
) -> None:
    torch.save(
        {
            "model_state": model.state_dict(),
            "token_to_id": token_to_id,
            "label_to_id": label_to_id,
            "id_to_label": id_to_label,
            "model_config": config_to_dict(config),
            "parameters": count_parameters(model),
            "metadata": metadata,
        },
        path,
    )


def load_best(path: Path, device: torch.device):
    from momentum_intent_model import load_checkpoint

    return load_checkpoint(path, device)


def prefix_keys(values: dict, prefix: str) -> dict:
    return {f"{prefix}{key}": value for key, value in values.items() if key != "confusion_matrix"}


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True


if __name__ == "__main__":
    main()
