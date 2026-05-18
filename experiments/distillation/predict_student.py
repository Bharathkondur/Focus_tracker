from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "training"))

from momentum_intent_model import load_checkpoint, predict  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict intent with the distilled student.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--model", default="experiments/distillation/latest/model.pt")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    device = select_device(args.device)
    model, token_to_id, id_to_label, config, _checkpoint = load_checkpoint(args.model, device)
    label, confidence, scores = predict(" ".join(args.text), model, token_to_id, id_to_label, config, device)
    print(f"{label}\tconfidence={confidence:.4f}\tscores={scores}")


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
