from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import torch
from torch import nn


LABELS = ("task", "goal", "note", "plan")
SPECIAL_TOKENS = ("[PAD]", "[UNK]", "[CLS]", "[SEP]")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?|[^\w\s]", re.IGNORECASE)


@dataclass(slots=True)
class ModelConfig:
    vocab_size: int
    max_length: int
    hidden_size: int = 192
    num_layers: int = 4
    num_heads: int = 6
    intermediate_size: int = 768
    dropout: float = 0.15


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def build_vocab(texts: Iterable[str], vocab_size: int) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for token in tokenize(text):
            counts[token] = counts.get(token, 0) + 1
    budget = max(0, vocab_size - len(SPECIAL_TOKENS))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return list(SPECIAL_TOKENS) + [token for token, _count in ranked[:budget]]


def encode_text(
    text: str,
    token_to_id: dict[str, int],
    max_length: int,
) -> tuple[list[int], list[int]]:
    unk_id = token_to_id["[UNK]"]
    pad_id = token_to_id["[PAD]"]
    tokens = ["[CLS]"] + tokenize(text)[: max_length - 2] + ["[SEP]"]
    ids = [token_to_id.get(token, unk_id) for token in tokens]
    mask = [1] * len(ids)
    if len(ids) < max_length:
        padding = max_length - len(ids)
        ids.extend([pad_id] * padding)
        mask.extend([0] * padding)
    return ids[:max_length], mask[:max_length]


class IntentDataset(torch.utils.data.Dataset):
    def __init__(
        self,
        rows: list[dict[str, str]],
        token_to_id: dict[str, int],
        label_to_id: dict[str, int],
        max_length: int,
    ) -> None:
        self.input_ids: list[list[int]] = []
        self.attention_mask: list[list[int]] = []
        self.labels: list[int] = []
        for row in rows:
            ids, mask = encode_text(row["text"], token_to_id, max_length)
            self.input_ids.append(ids)
            self.attention_mask.append(mask)
            self.labels.append(label_to_id[row["label"]])

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor(self.input_ids[index], dtype=torch.long),
            "attention_mask": torch.tensor(self.attention_mask[index], dtype=torch.bool),
            "labels": torch.tensor(self.labels[index], dtype=torch.long),
        }


class MomentumIntentEncoder(nn.Module):
    def __init__(self, config: ModelConfig, num_labels: int) -> None:
        super().__init__()
        self.token_embedding = nn.Embedding(config.vocab_size, config.hidden_size)
        self.position_embedding = nn.Embedding(config.max_length, config.hidden_size)
        layer = nn.TransformerEncoderLayer(
            d_model=config.hidden_size,
            nhead=config.num_heads,
            dim_feedforward=config.intermediate_size,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer,
            num_layers=config.num_layers,
            enable_nested_tensor=False,
        )
        self.norm = nn.LayerNorm(config.hidden_size)
        self.dropout = nn.Dropout(config.dropout)
        self.classifier = nn.Linear(config.hidden_size, num_labels)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(input_ids.size(1), device=input_ids.device).unsqueeze(0)
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
        hidden = self.encoder(hidden, src_key_padding_mask=~attention_mask)
        cls_hidden = self.norm(hidden[:, 0])
        return self.classifier(self.dropout(cls_hidden))


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def load_checkpoint(path: str | Path, device: str | torch.device = "cpu") -> tuple[
    MomentumIntentEncoder,
    dict[str, int],
    dict[int, str],
    ModelConfig,
    dict,
]:
    checkpoint = torch.load(path, map_location=device)
    config = ModelConfig(**checkpoint["model_config"])
    id_to_label = {int(key): value for key, value in checkpoint["id_to_label"].items()}
    token_to_id = checkpoint["token_to_id"]
    model = MomentumIntentEncoder(config, len(id_to_label))
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()
    return model, token_to_id, id_to_label, config, checkpoint


@torch.inference_mode()
def predict(
    text: str,
    model: MomentumIntentEncoder,
    token_to_id: dict[str, int],
    id_to_label: dict[int, str],
    config: ModelConfig,
    device: str | torch.device = "cpu",
) -> tuple[str, float, dict[str, float]]:
    ids, mask = encode_text(text, token_to_id, config.max_length)
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    attention_mask = torch.tensor([mask], dtype=torch.bool, device=device)
    probabilities = torch.softmax(model(input_ids, attention_mask), dim=-1)[0]
    best_id = int(torch.argmax(probabilities).item())
    scores = {
        id_to_label[index]: round(float(probabilities[index].item()), 4)
        for index in range(len(id_to_label))
    }
    return id_to_label[best_id], round(float(probabilities[best_id].item()), 4), scores


def save_json(path: str | Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def config_to_dict(config: ModelConfig) -> dict:
    return asdict(config)
