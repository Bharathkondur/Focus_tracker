from __future__ import annotations

import math
from collections import Counter, defaultdict


KINDS = ("task", "goal", "note")


class TinyIntentClassifier:
    """A tiny CPU-only classifier trained from saved capture events.

    This is intentionally simple: hashed lexical features with a naive Bayes
    scorer. It is small enough to rebuild on demand and acts as the local
    learning layer before any heavier model is considered.
    """

    def __init__(self, examples: list[tuple[str, str]]):
        self.examples = [(text, kind) for text, kind in examples if kind in KINDS and text.strip()]
        self.kind_counts = Counter(kind for _text, kind in self.examples)
        self.feature_counts: dict[str, Counter[str]] = {kind: Counter() for kind in KINDS}
        self.totals = Counter()
        self.vocabulary = set()
        for text, kind in self.examples:
            features = _features(text)
            self.feature_counts[kind].update(features)
            self.totals[kind] += sum(features.values())
            self.vocabulary.update(features)

    @property
    def ready(self) -> bool:
        return len(self.examples) >= 8 and len(self.kind_counts) >= 2

    def predict(self, text: str) -> tuple[str, float]:
        if not self.ready:
            return "", 0.0
        features = _features(text)
        if not features:
            return "", 0.0
        scores = {}
        total_examples = len(self.examples)
        vocab_size = max(1, len(self.vocabulary))
        for kind in KINDS:
            prior = (self.kind_counts[kind] + 1) / (total_examples + len(KINDS))
            score = math.log(prior)
            denominator = self.totals[kind] + vocab_size
            for feature, count in features.items():
                likelihood = (self.feature_counts[kind][feature] + 1) / denominator
                score += count * math.log(likelihood)
            scores[kind] = score
        best = max(scores, key=scores.get)
        confidence = _softmax_confidence(scores, best)
        return best, confidence


def _features(text: str) -> Counter[str]:
    normalized = " ".join(text.lower().split())
    words = [_clean(word) for word in normalized.split()]
    words = [word for word in words if word]
    features: Counter[str] = Counter()
    for word in words:
        features[f"w:{word}"] += 1
        if len(word) >= 4:
            features[f"p:{word[:4]}"] += 1
            features[f"s:{word[-4:]}"] += 1
    for first, second in zip(words, words[1:]):
        features[f"b:{first}_{second}"] += 1
    return features


def _clean(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum())


def _softmax_confidence(scores: dict[str, float], best: str) -> float:
    peak = max(scores.values())
    exps = {kind: math.exp(value - peak) for kind, value in scores.items()}
    total = sum(exps.values())
    if total <= 0:
        return 0.0
    return round(exps[best] / total, 3)
