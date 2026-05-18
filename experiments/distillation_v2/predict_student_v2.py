from __future__ import annotations

import argparse
from pathlib import Path

import torch

from student_bpe_model import load_checkpoint, load_tokenizer, predict


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict intent with Distilled Student v2.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--model-dir", default="experiments/distillation_v2/latest")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    device = select_device(args.device)
    model_dir = Path(args.model_dir)
    model, config, id_to_label, _checkpoint = load_checkpoint(model_dir / "model.pt", device)
    tokenizer = load_tokenizer(model_dir / "tokenizer.json")
    label, confidence, scores = predict(" ".join(args.text), model, tokenizer, config, id_to_label, device)
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
