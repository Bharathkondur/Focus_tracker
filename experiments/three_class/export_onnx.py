from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import BpeIntentEncoder, StudentConfig  # noqa: E402


def main() -> None:
    args = parse_args()
    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_path = checkpoint_dir / "model.pt"
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Missing checkpoint: {checkpoint_path}")
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    config = StudentConfig(**checkpoint["model_config"])
    labels = checkpoint["id_to_label"]
    model = BpeIntentEncoder(config, len(labels))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    input_ids = torch.ones((1, config.max_length), dtype=torch.long)
    attention_mask = torch.ones((1, config.max_length), dtype=torch.bool)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        (input_ids, attention_mask),
        output,
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch"},
            "attention_mask": {0: "batch"},
            "logits": {0: "batch"},
        },
        opset_version=args.opset,
    )
    print(f"Exported ONNX model to {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the 3-class Momentum model to ONNX for optional CPU runtime testing.")
    parser.add_argument("--checkpoint-dir", default="experiments/three_class/latest")
    parser.add_argument("--output", default="experiments/three_class/latest/model.onnx")
    parser.add_argument("--opset", type=int, default=17)
    return parser.parse_args()


if __name__ == "__main__":
    main()
