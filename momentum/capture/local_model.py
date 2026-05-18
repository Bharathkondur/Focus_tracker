from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from momentum.data.paths import BASE_DIR


MODEL_DIR = BASE_DIR / "experiments" / "three_class" / "latest"
KINDS = ("task", "goal", "note")


@dataclass(slots=True)
class ModelPrediction:
    kind: str
    confidence: float
    scores: dict[str, float]
    status: str


class LocalIntentModel:
    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir or MODEL_DIR
        self._loaded = False
        self._available = False
        self._status = "Local AI not loaded yet."
        self._torch = None
        self._tokenizer = None
        self._model = None
        self._config = None
        self._id_to_label: dict[int, str] = {}
        self._device = "cpu"

    @property
    def status(self) -> str:
        if not self._loaded:
            self._load()
        return self._status

    @property
    def available(self) -> bool:
        if not self._loaded:
            self._load()
        return self._available

    def predict(self, text: str) -> ModelPrediction | None:
        if not text.strip():
            return None
        if not self._loaded:
            self._load()
        if not self._available:
            return None
        try:
            ids, mask = self._encode(text)
            torch = self._torch
            input_ids = torch.tensor([ids], dtype=torch.long, device=self._device)
            attention_mask = torch.tensor([mask], dtype=torch.bool, device=self._device)
            with torch.inference_mode():
                probabilities = torch.softmax(self._model(input_ids, attention_mask), dim=-1)[0]
            best_id = int(torch.argmax(probabilities).item())
            scores = {
                self._id_to_label[index]: round(float(probabilities[index].item()), 4)
                for index in range(len(self._id_to_label))
            }
            best = self._id_to_label[best_id]
            return ModelPrediction(best, scores[best], scores, self._status)
        except Exception as exc:
            self._available = False
            self._status = f"Local AI disabled after prediction error: {exc}"
            return None

    def _load(self) -> None:
        self._loaded = True
        model_path = self.model_dir / "model.pt"
        tokenizer_path = self.model_dir / "tokenizer.json"
        if not model_path.exists() or not tokenizer_path.exists():
            self._status = "Local AI checkpoint missing; using rules and memory."
            return
        try:
            import torch
            from tokenizers import Tokenizer

            self._torch = torch
            checkpoint = torch.load(model_path, map_location="cpu")
            self._config = _StudentConfig(**checkpoint["model_config"])
            self._id_to_label = {int(key): value for key, value in checkpoint["id_to_label"].items()}
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
            self._model = _BpeIntentEncoder(self._config, len(self._id_to_label))
            self._model.load_state_dict(checkpoint["model_state"])
            self._model.eval()
            torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
            self._available = True
            self._status = "Three-class local AI loaded."
        except Exception as exc:
            self._status = f"Local AI unavailable: {exc}"
            self._available = False

    def _encode(self, text: str) -> tuple[list[int], list[int]]:
        encoded = self._tokenizer.encode(text)
        ids = encoded.ids[: self._config.max_length]
        mask = [1] * len(ids)
        pad_id = self._tokenizer.token_to_id("[PAD]")
        if len(ids) < self._config.max_length:
            padding = self._config.max_length - len(ids)
            ids.extend([pad_id] * padding)
            mask.extend([0] * padding)
        return ids[: self._config.max_length], mask[: self._config.max_length]


@dataclass(slots=True)
class _StudentConfig:
    vocab_size: int
    max_length: int = 48
    hidden_size: int = 320
    num_layers: int = 6
    num_heads: int = 8
    intermediate_size: int = 1280
    dropout: float = 0.12


def _torch_modules():
    import torch
    from torch import nn

    return torch, nn


class _BpeIntentEncoder:
    def __new__(cls, config: _StudentConfig, num_labels: int):
        torch, nn = _torch_modules()

        class Encoder(nn.Module):
            def __init__(self):
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

            def forward(self, input_ids, attention_mask):
                positions = torch.arange(input_ids.size(1), device=input_ids.device).unsqueeze(0)
                hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
                hidden = self.encoder(hidden, src_key_padding_mask=~attention_mask)
                cls_hidden = self.norm(hidden[:, 0])
                return self.classifier(self.dropout(cls_hidden))

        return Encoder()
