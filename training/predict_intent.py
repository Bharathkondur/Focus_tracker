from __future__ import annotations

import argparse
from pathlib import Path

import torch

from momentum_intent_model import load_checkpoint, predict


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict a Momentum intent with a trained checkpoint.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--model", default="models/momentum_intent/latest/model.pt")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    device = select_device(args.device)
    model, token_to_id, id_to_label, config, _checkpoint = load_checkpoint(Path(args.model), device)
    label, confidence, scores = predict(
        " ".join(args.text),
        model,
        token_to_id,
        id_to_label,
        config,
        device,
    )
    print(f"{label}\tconfidence={confidence:.4f}\tscores={scores}")


def select_device(choice: str) -> torch.device:
    if choice == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but this Python environment has CPU-only PyTorch.")
        return torch.device("cuda")
    if choice == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


if __name__ == "__main__":
    main()
