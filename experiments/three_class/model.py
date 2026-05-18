from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from tokenizers import Tokenizer
from tokenizers.decoders import ByteLevel as ByteLevelDecoder
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.processors import TemplateProcessing
from tokenizers.trainers import BpeTrainer
from torch import nn


LABELS = ("task", "goal", "note")
SPECIAL_TOKENS = ("[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]")


@dataclass(slots=True)
class StudentConfig:
    vocab_size: int
    max_length: int = 48
    hidden_size: int = 320
    num_layers: int = 6
    num_heads: int = 8
    intermediate_size: int = 1280
    dropout: float = 0.12


def train_bpe_tokenizer(texts: list[str], vocab_size: int, output_path: str | Path) -> Tokenizer:
    tokenizer = Tokenizer(BPE(unk_token="[UNK]"))
    tokenizer.pre_tokenizer = ByteLevel(add_prefix_space=False)
    tokenizer.decoder = ByteLevelDecoder()
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=2,
        special_tokens=list(SPECIAL_TOKENS),
        show_progress=False,
    )
    tokenizer.train_from_iterator(texts, trainer=trainer)
    tokenizer.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]",
        special_tokens=[
            ("[CLS]", tokenizer.token_to_id("[CLS]")),
            ("[SEP]", tokenizer.token_to_id("[SEP]")),
        ],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    tokenizer.save(str(output_path))
    return tokenizer


def load_tokenizer(path: str | Path) -> Tokenizer:
    return Tokenizer.from_file(str(path))


def encode_text(tokenizer: Tokenizer, text: str, max_length: int) -> tuple[list[int], list[int]]:
    encoded = tokenizer.encode(text)
    ids = encoded.ids[:max_length]
    mask = [1] * len(ids)
    pad_id = tokenizer.token_to_id("[PAD]")
    if len(ids) < max_length:
        padding = max_length - len(ids)
        ids.extend([pad_id] * padding)
        mask.extend([0] * padding)
    return ids[:max_length], mask[:max_length]


class DistillDataset(torch.utils.data.Dataset):
    def __init__(self, rows: list[dict], tokenizer: Tokenizer, label_to_id: dict[str, int], max_length: int):
        self.rows = rows
        self.tokenizer = tokenizer
        self.label_to_id = label_to_id
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        row = self.rows[index]
        ids, mask = encode_text(self.tokenizer, row["text"], self.max_length)
        return {
            "input_ids": torch.tensor(ids, dtype=torch.long),
            "attention_mask": torch.tensor(mask, dtype=torch.bool),
            "labels": torch.tensor(self.label_to_id[row["label"]], dtype=torch.long),
            "teacher_logits": torch.tensor(row["teacher_logits"], dtype=torch.float),
            "source_weight": torch.tensor(row.get("source_weight", 1.0), dtype=torch.float),
        }


class BpeIntentEncoder(nn.Module):
    def __init__(self, config: StudentConfig, num_labels: int) -> None:
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
        self.encoder = nn.TransformerEncoder(layer, num_layers=config.num_layers, enable_nested_tensor=False)
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


def config_to_dict(config: StudentConfig) -> dict:
    return asdict(config)


def save_json(path: str | Path, value: object) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def save_checkpoint(path, model, config, label_to_id, id_to_label, metadata) -> None:
    torch.save(
        {
            "model_state": model.state_dict(),
            "model_config": config_to_dict(config),
            "label_to_id": label_to_id,
            "id_to_label": id_to_label,
            "parameters": count_parameters(model),
            "metadata": metadata,
        },
        path,
    )
