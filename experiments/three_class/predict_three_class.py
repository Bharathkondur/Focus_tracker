from __future__ import annotations

import argparse
from pathlib import Path

import torch

from model import BpeIntentEncoder, StudentConfig, encode_text, load_tokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict with the 3-class Momentum model.")
    parser.add_argument("text", nargs="+")
    parser.add_argument("--model-dir", default="experiments/three_class/latest")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    device = select_device(args.device)
    model_dir = Path(args.model_dir)
    checkpoint = torch.load(model_dir / "model.pt", map_location=device)
    config = StudentConfig(**checkpoint["model_config"])
    id_to_label = {int(key): value for key, value in checkpoint["id_to_label"].items()}
    tokenizer = load_tokenizer(model_dir / "tokenizer.json")
    model = BpeIntentEncoder(config, len(id_to_label)).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    ids, mask = encode_text(tokenizer, " ".join(args.text), config.max_length)
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    attention_mask = torch.tensor([mask], dtype=torch.bool, device=device)
    with torch.inference_mode():
        probabilities = torch.softmax(model(input_ids, attention_mask), dim=-1)[0]
    best = int(torch.argmax(probabilities).item())
    scores = {id_to_label[index]: round(float(probabilities[index].item()), 4) for index in range(len(id_to_label))}
    print(f"{id_to_label[best]}\tconfidence={scores[id_to_label[best]]:.4f}\tscores={scores}")


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
