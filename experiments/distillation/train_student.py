from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from torch import nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "training"))

from momentum_intent_model import (  # noqa: E402
    LABELS,
    ModelConfig,
    MomentumIntentEncoder,
    build_vocab,
    config_to_dict,
    count_parameters,
    encode_text,
)


class DistillDataset(Dataset):
    def __init__(
        self,
        rows: list[dict],
        token_to_id: dict[str, int],
        label_to_id: dict[str, int],
        max_length: int,
    ) -> None:
        self.rows = rows
        self.token_to_id = token_to_id
        self.label_to_id = label_to_id
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.rows[index]
        ids, mask = encode_text(row["text"], self.token_to_id, self.max_length)
        return {
            "input_ids": torch.tensor(ids, dtype=torch.long),
            "attention_mask": torch.tensor(mask, dtype=torch.bool),
            "labels": torch.tensor(self.label_to_id[row["label"]], dtype=torch.long),
            "teacher_logits": torch.tensor(row["teacher_logits"], dtype=torch.float),
            "source_weight": torch.tensor(row.get("source_weight", 1.0), dtype=torch.float),
        }


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    output_dir = Path(args.output_dir) / (args.run_name or time.strftime("%Y%m%d_%H%M%S"))
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_cache(Path(args.cache), args.personal_weight)
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
    model = MomentumIntentEncoder(config, len(LABELS)).to(device)

    train_loader = DataLoader(
        DistillDataset(train_rows, token_to_id, label_to_id, args.max_length),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        DistillDataset(val_rows, token_to_id, label_to_id, args.max_length),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=0,
    )
    test_loader = DataLoader(
        DistillDataset(test_rows, token_to_id, label_to_id, args.max_length),
        batch_size=args.eval_batch_size,
        shuffle=False,
        num_workers=0,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    total_steps = max(1, len(train_loader) * args.epochs)
    warmup_steps = max(1, int(total_steps * args.warmup_ratio))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer,
        lr_lambda=lambda step: lr_schedule(step, warmup_steps, total_steps),
    )
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
    write_json(output_dir / "training_metadata.json", metadata)
    write_json(output_dir / "vocab.json", vocab)
    write_json(output_dir / "label_to_id.json", label_to_id)

    print(f"Cache: {args.cache}")
    print(f"Rows: train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")
    print(f"Labels: {dict(Counter(row['label'] for row in rows))}")
    print(f"Sources: {dict(Counter(row['source'] for row in rows))}")
    print(f"Device: {device} amp={use_amp}")
    print(f"Parameters: {metadata['parameters']:,}")

    best_macro_f1 = -1.0
    best_epoch = 0
    history = []
    started = time.time()
    for epoch in range(1, args.epochs + 1):
        train_metrics = train_one_epoch(
            model,
            train_loader,
            optimizer,
            scheduler,
            scaler,
            device,
            use_amp,
            args,
        )
        val_metrics = evaluate(model, val_loader, device)
        history.append({"epoch": epoch, **train_metrics, **prefix(val_metrics, "val_")})
        print(
            f"epoch {epoch:02d} "
            f"loss={train_metrics['train_loss']:.4f} "
            f"hard={train_metrics['hard_loss']:.4f} "
            f"soft={train_metrics['soft_loss']:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} "
            f"val_macro_f1={val_metrics['macro_f1']:.4f}"
        )
        if val_metrics["macro_f1"] > best_macro_f1:
            best_macro_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            save_checkpoint(output_dir / "model.pt", model, token_to_id, label_to_id, id_to_label, config, metadata)

    model, token_to_id, id_to_label, config = load_checkpoint(output_dir / "model.pt", device)
    val_metrics = evaluate(model, val_loader, device)
    test_metrics = evaluate(model, test_loader, device)
    result = {
        "best_epoch": best_epoch,
        "best_val_macro_f1": best_macro_f1,
        "val": val_metrics,
        "test": test_metrics,
        "history": history,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    write_json(output_dir / "metrics.json", result)

    latest_dir = output_dir.parent.parent / "latest"
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(output_dir, latest_dir)

    print("Saved:", output_dir)
    print("Latest:", latest_dir)
    print(f"Test accuracy={test_metrics['accuracy']:.4f} macro_f1={test_metrics['macro_f1']:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a distilled scratch student from ModernBERT teacher logits.")
    parser.add_argument("--cache", default="experiments/distillation/cache/teacher_modernbert_cache.jsonl")
    parser.add_argument("--output-dir", default="experiments/distillation/runs")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--eval-batch-size", type=int, default=512)
    parser.add_argument("--learning-rate", type=float, default=4e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.08)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--test-split", type=float, default=0.1)
    parser.add_argument("--vocab-size", type=int, default=12000)
    parser.add_argument("--max-length", type=int, default=48)
    parser.add_argument("--hidden-size", type=int, default=256)
    parser.add_argument("--num-layers", type=int, default=6)
    parser.add_argument("--num-heads", type=int, default=8)
    parser.add_argument("--intermediate-size", type=int, default=1024)
    parser.add_argument("--dropout", type=float, default=0.12)
    parser.add_argument("--temperature", type=float, default=3.0)
    parser.add_argument("--hard-weight", type=float, default=0.45)
    parser.add_argument("--soft-weight", type=float, default=0.55)
    parser.add_argument("--personal-weight", type=float, default=1.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def load_cache(path: Path, personal_weight: float) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        text = " ".join(str(row.get("text", "")).strip().split())
        label = row.get("label")
        logits = row.get("teacher_logits")
        source = row.get("source", "base")
        if label not in LABELS or not text or not isinstance(logits, list) or len(logits) != len(LABELS):
            raise ValueError(f"Bad row at {path}:{line_number}")
        rows.append(
            {
                "text": text,
                "label": label,
                "teacher_logits": [float(value) for value in logits],
                "source": source,
                "source_weight": personal_weight if source == "personal" else 1.0,
            }
        )
    return rows


def stratified_split(rows: list[dict], val_split: float, test_split: float, seed: int):
    by_label: dict[str, list[dict]] = defaultdict(list)
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
    return max(0.05, 0.5 * (1.0 + torch.cos(torch.tensor(torch.pi * progress))).item())


def train_one_epoch(model, loader, optimizer, scheduler, scaler, device, use_amp, args) -> dict:
    model.train()
    hard_fn = nn.CrossEntropyLoss(reduction="none", label_smoothing=0.02)
    kl_fn = nn.KLDivLoss(reduction="none")
    total_loss = 0.0
    total_hard = 0.0
    total_soft = 0.0
    total = 0
    temperature = args.temperature

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
            teacher_probs = torch.softmax(teacher_logits / temperature, dim=-1)
            student_log_probs = torch.log_softmax(student_logits / temperature, dim=-1)
            soft_loss_per = kl_fn(student_log_probs, teacher_probs).sum(dim=-1) * (temperature**2)
            loss_per = args.hard_weight * hard_loss_per + args.soft_weight * soft_loss_per
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

    return {
        "train_loss": total_loss / max(1, total),
        "hard_loss": total_hard / max(1, total),
        "soft_loss": total_soft / max(1, total),
    }


@torch.inference_mode()
def evaluate(model, loader, device) -> dict:
    model.eval()
    predictions = []
    targets = []
    total = 0
    total_loss = 0.0
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


def save_checkpoint(path, model, token_to_id, label_to_id, id_to_label, config, metadata) -> None:
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


def load_checkpoint(path, device):
    checkpoint = torch.load(path, map_location=device)
    config = ModelConfig(**checkpoint["model_config"])
    id_to_label = {int(key): value for key, value in checkpoint["id_to_label"].items()}
    token_to_id = checkpoint["token_to_id"]
    model = MomentumIntentEncoder(config, len(id_to_label))
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()
    return model, token_to_id, id_to_label, config


def prefix(values: dict, name: str) -> dict:
    return {f"{name}{key}": value for key, value in values.items() if key != "confusion_matrix"}


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
