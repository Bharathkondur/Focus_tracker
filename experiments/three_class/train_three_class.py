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
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch import nn
from torch.utils.data import DataLoader

from model import (
    LABELS,
    BpeIntentEncoder,
    DistillDataset,
    StudentConfig,
    config_to_dict,
    count_parameters,
    load_tokenizer,
    save_checkpoint,
    save_json,
    train_bpe_tokenizer,
)


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    output_dir = Path(args.output_dir) / (args.run_name or time.strftime("%Y%m%d_%H%M%S"))
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_cache(Path(args.cache), args.personal_weight, args.hard_weight_source)
    train_rows, val_rows, test_rows = stratified_split(rows, args.val_split, args.test_split, args.seed)
    tokenizer = train_bpe_tokenizer([row["text"] for row in train_rows], args.vocab_size, output_dir / "tokenizer.json")
    label_to_id = {label: index for index, label in enumerate(LABELS)}
    id_to_label = {index: label for label, index in label_to_id.items()}
    config = StudentConfig(
        vocab_size=tokenizer.get_vocab_size(),
        max_length=args.max_length,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        num_heads=args.num_heads,
        intermediate_size=args.intermediate_size,
        dropout=args.dropout,
    )
    device = select_device(args.device)
    use_amp = args.amp and device.type == "cuda"
    model = BpeIntentEncoder(config, len(LABELS)).to(device)

    train_loader = DataLoader(DistillDataset(train_rows, tokenizer, label_to_id, config.max_length), batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(DistillDataset(val_rows, tokenizer, label_to_id, config.max_length), batch_size=args.eval_batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(DistillDataset(test_rows, tokenizer, label_to_id, config.max_length), batch_size=args.eval_batch_size, shuffle=False, num_workers=0)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda step: lr_schedule(step, warmup_steps, total_steps))
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    metadata = {
        "cache": args.cache,
        "rows": {"total": len(rows), "train": len(train_rows), "val": len(val_rows), "test": len(test_rows)},
        "labels": LABELS,
        "model_config": config_to_dict(config),
        "parameters": count_parameters(model),
        "device": str(device),
        "use_amp": use_amp,
        "args": vars(args),
    }
    save_json(output_dir / "training_metadata.json", metadata)
    save_json(output_dir / "label_to_id.json", label_to_id)

    print(f"Cache: {args.cache}")
    print(f"Rows: train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")
    print(f"Labels: {dict(Counter(row['label'] for row in rows))}")
    print(f"Sources: {dict(Counter(row['source'] for row in rows))}")
    print(f"BPE vocab: {config.vocab_size}")
    print(f"Device: {device} amp={use_amp}")
    print(f"Parameters: {metadata['parameters']:,}")

    best_macro_f1 = -1.0
    best_epoch = 0
    best_checkpoint = output_dir / "model.pt"
    stale_epochs = 0
    history = []
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        train_metrics = train_one_epoch(model, train_loader, optimizer, scheduler, scaler, device, use_amp, args)
        val_metrics = evaluate(model, val_loader, device)
        history.append({"epoch": epoch, **train_metrics, **prefix(val_metrics, "val_")})
        print(
            f"epoch {epoch:02d} loss={train_metrics['train_loss']:.4f} "
            f"hard={train_metrics['hard_loss']:.4f} soft={train_metrics['soft_loss']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} val_macro_f1={val_metrics['macro_f1']:.4f}"
        )
        if val_metrics["macro_f1"] > best_macro_f1 + args.min_delta:
            best_macro_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            stale_epochs = 0
            best_checkpoint = output_dir / f"model_epoch_{epoch:02d}.pt"
            save_checkpoint(best_checkpoint, model, config, label_to_id, id_to_label, metadata)
        else:
            stale_epochs += 1
            if epoch >= args.min_epochs and stale_epochs >= args.patience:
                print(f"Early stopping at epoch {epoch}; best epoch {best_epoch}.")
                break

    final_model = output_dir / "model.pt"
    if final_model.exists():
        final_model.unlink()
    shutil.copyfile(best_checkpoint, final_model)
    checkpoint = torch.load(final_model, map_location=device)
    best_model = BpeIntentEncoder(StudentConfig(**checkpoint["model_config"]), len(LABELS)).to(device)
    best_model.load_state_dict(checkpoint["model_state"])
    best_model.eval()
    val_metrics = evaluate(best_model, val_loader, device)
    test_metrics = evaluate(best_model, test_loader, device)
    result = {
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_macro_f1,
        "val": val_metrics,
        "test": test_metrics,
        "history": history,
        "elapsed_seconds": round(time.time() - started, 2),
        "checkpoint_parameters": checkpoint["parameters"],
    }
    save_json(output_dir / "metrics.json", result)
    save_json(output_dir / "model_config.json", checkpoint["model_config"])

    latest_dir = output_dir.parent.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(output_dir, latest_dir)
    print("Saved:", output_dir)
    print("Latest:", latest_dir)
    print(f"Test accuracy={test_metrics['accuracy']:.4f} macro_f1={test_metrics['macro_f1']:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the 3-class Momentum model.")
    parser.add_argument("--cache", default="experiments/three_class/cache/three_class_cache.jsonl")
    parser.add_argument("--output-dir", default="experiments/three_class/runs")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--epochs", type=int, default=36)
    parser.add_argument("--min-epochs", type=int, default=16)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--min-delta", type=float, default=0.0002)
    parser.add_argument("--batch-size", type=int, default=192)
    parser.add_argument("--eval-batch-size", type=int, default=384)
    parser.add_argument("--learning-rate", type=float, default=3.5e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.08)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--vocab-size", type=int, default=10000)
    parser.add_argument("--max-length", type=int, default=48)
    parser.add_argument("--hidden-size", type=int, default=320)
    parser.add_argument("--num-layers", type=int, default=6)
    parser.add_argument("--num-heads", type=int, default=8)
    parser.add_argument("--intermediate-size", type=int, default=1280)
    parser.add_argument("--dropout", type=float, default=0.12)
    parser.add_argument("--temperature", type=float, default=2.3)
    parser.add_argument("--hard-loss-weight", type=float, default=0.62)
    parser.add_argument("--soft-loss-weight", type=float, default=0.38)
    parser.add_argument("--personal-weight", type=float, default=1.55)
    parser.add_argument("--hard-weight-source", type=float, default=1.45)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def load_cache(path: Path, personal_weight: float, hard_weight: float) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        label = row.get("label")
        if label not in LABELS:
            raise ValueError(f"Bad row at {path}:{line_number}")
        source = row.get("source", "base")
        source_weight = personal_weight if source == "personal" else hard_weight if source == "hard" else 1.0
        rows.append(
            {
                "text": row["text"],
                "label": label,
                "teacher_logits": [float(value) for value in row["teacher_logits"]],
                "source": source,
                "source_weight": source_weight,
            }
        )
    return rows


def stratified_split(rows: list[dict], val_split: float, test_split: float, seed: int):
    by_label = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row)
    rng = random.Random(seed)
    train_rows = []
    val_rows = []
    test_rows = []
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
            raise RuntimeError("CUDA was requested, but CUDA is not available.")
        return torch.device("cuda")
    if choice == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def lr_schedule(step: int, warmup_steps: int, total_steps: int) -> float:
    if step < warmup_steps:
        return max(0.05, step / max(1, warmup_steps))
    progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
    return max(0.05, 0.5 * (1.0 + math.cos(math.pi * progress)))


def train_one_epoch(model, loader, optimizer, scheduler, scaler, device, use_amp, args) -> dict:
    model.train()
    hard_fn = nn.CrossEntropyLoss(reduction="none", label_smoothing=0.02)
    kl_fn = nn.KLDivLoss(reduction="none")
    total_loss = total_hard = total_soft = 0.0
    total = 0
    for batch in loader:
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attention_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        teacher_logits = batch["teacher_logits"].to(device, non_blocking=True)
        source_weight = batch["source_weight"].to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            student_logits = model(input_ids, attention_mask)
            hard_loss_per = hard_fn(student_logits, labels)
            teacher_probs = torch.softmax(teacher_logits / args.temperature, dim=-1)
            student_log_probs = torch.log_softmax(student_logits / args.temperature, dim=-1)
            soft_loss_per = kl_fn(student_log_probs, teacher_probs).sum(dim=-1) * (args.temperature**2)
            loss_per = args.hard_loss_weight * hard_loss_per + args.soft_loss_weight * soft_loss_per
            loss = (loss_per * source_weight).mean()
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        if args.grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()
        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        total_hard += float(hard_loss_per.mean().item()) * batch_size
        total_soft += float(soft_loss_per.mean().item()) * batch_size
        total += batch_size
    return {"train_loss": total_loss / total, "hard_loss": total_hard / total, "soft_loss": total_soft / total}


@torch.inference_mode()
def evaluate(model, loader, device) -> dict:
    model.eval()
    predictions = []
    targets = []
    total_loss = 0.0
    total = 0
    loss_fn = nn.CrossEntropyLoss()
    for batch in loader:
        input_ids = batch["input_ids"].to(device, non_blocking=True)
        attention_mask = batch["attention_mask"].to(device, non_blocking=True)
        labels = batch["labels"].to(device, non_blocking=True)
        logits = model(input_ids, attention_mask)
        loss = loss_fn(logits, labels)
        pred = torch.argmax(logits, dim=-1)
        batch_size = labels.size(0)
        total_loss += float(loss.item()) * batch_size
        total += batch_size
        predictions.extend(int(value) for value in pred.cpu().tolist())
        targets.extend(int(value) for value in labels.cpu().tolist())
    report = classification_report(targets, predictions, target_names=LABELS, output_dict=True, zero_division=0)
    return {
        "loss": total_loss / max(1, total),
        "accuracy": accuracy_score(targets, predictions),
        "macro_f1": f1_score(targets, predictions, average="macro"),
        "per_label": {label: report[label] for label in LABELS},
        "confusion_matrix": confusion_matrix(targets, predictions).tolist(),
    }


def prefix(values: dict, name: str) -> dict:
    return {f"{name}{key}": value for key, value in values.items() if key != "confusion_matrix"}


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True


if __name__ == "__main__":
    main()
