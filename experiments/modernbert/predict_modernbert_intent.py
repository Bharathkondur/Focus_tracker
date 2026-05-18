from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict Momentum intent with a ModernBERT experiment.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--model-dir", default="experiments/modernbert/latest")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--max-length", type=int, default=64)
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    device = select_device(args.device)
    model_dir = Path(args.model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=args.trust_remote_code)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_dir,
        trust_remote_code=args.trust_remote_code,
    ).to(device)
    model.eval()

    text = " ".join(args.text)
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=args.max_length,
        padding="max_length",
        return_tensors="pt",
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.inference_mode():
        probabilities = torch.softmax(model(**encoded).logits[0], dim=-1)

    id_to_label = {int(key): value for key, value in model.config.id2label.items()}
    best = int(torch.argmax(probabilities).item())
    scores = {
        id_to_label[index]: round(float(probabilities[index].item()), 4)
        for index in range(len(id_to_label))
    }
    print(f"{id_to_label[best]}\tconfidence={scores[id_to_label[best]]:.4f}\tscores={json.dumps(scores)}")


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
