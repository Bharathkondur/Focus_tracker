from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

from momentum.capture.classifier import TinyIntentClassifier
from momentum.capture.intent import CaptureIntent, parse_capture
from momentum.capture.local_model import LocalIntentModel
from momentum.capture.memory import CaptureMemory, MemoryItem
from momentum.core.dates import today


EXPLICIT_RE = re.compile(r"^\s*(task|todo|goal|habit|note|notes|plan)\s*[:\-]", re.IGNORECASE)
ACTION_WORDS = {
    "apply", "buy", "call", "complete", "email", "finish", "fix", "pay",
    "prepare", "review", "send", "submit", "write",
}
GOAL_WORDS = {"daily", "habit", "goal", "everyday", "routine", "consistency"}
NOTE_WORDS = {"felt", "feeling", "remember", "note", "journal", "observed", "thought"}
NOTE_CONTEXT_WORDS = {"plan", "outline", "strategy", "roadmap"}


@dataclass(slots=True)
class RoutedCapture:
    intent: CaptureIntent
    confidence: float
    source: str
    context: list[MemoryItem]

    @property
    def needs_confirmation(self) -> bool:
        return self.confidence < 0.72

    @property
    def summary(self) -> str:
        source = self.source.replace("_", " ")
        suffix = " - confirm before saving" if self.needs_confirmation else ""
        return f"{self.intent.label}. Confidence {self.confidence:.0%} from {source}{suffix}."


class ContextRouter:
    def __init__(
        self,
        memory: CaptureMemory,
        local_model: LocalIntentModel | None = None,
        preload_model: bool = True,
    ):
        self.memory = memory
        self.local_model = local_model or LocalIntentModel()
        self._classifier: TinyIntentClassifier | None = None
        self._classifier_version: tuple[int, int] | None = None
        if preload_model:
            self.local_model.warmup_async()

    @property
    def ai_status(self) -> str:
        return self.local_model.status

    def route(
        self,
        value: str,
        base_day: date | None = None,
        forced_kind: str = "auto",
    ) -> RoutedCapture | None:
        base = base_day or today()
        intent = parse_capture(value, base)
        if intent is None:
            return None

        context = self.memory.related(intent.text)
        if forced_kind != "auto":
            return RoutedCapture(replace(intent, kind=forced_kind), 0.99, "user_mode", context)

        explicit = EXPLICIT_RE.search(value)
        if explicit:
            return RoutedCapture(intent, 0.98, "explicit_prefix", context)

        rule_kind, rule_confidence = self._rule_score(intent, value, base)
        memory_kind, memory_confidence = self._memory_score(context)
        model_prediction = self.local_model.predict(intent.text)
        model_kind, model_confidence = self._model_score(model_prediction)
        classifier_kind, classifier_confidence = self._tiny_classifier().predict(intent.text)

        candidates = [
            (intent.kind, 0.58, "parser_default"),
            (rule_kind, rule_confidence, "rules"),
            (memory_kind, memory_confidence, "memory"),
            (model_kind, model_confidence, "three_class_ai"),
            (classifier_kind, classifier_confidence, "tiny_classifier"),
        ]
        kind, confidence, source = max(
            (candidate for candidate in candidates if candidate[0]),
            key=lambda candidate: candidate[1],
        )
        return RoutedCapture(replace(intent, kind=kind), confidence, source, context)

    def _rule_score(self, intent: CaptureIntent, raw: str, base_day: date) -> tuple[str, float]:
        words = set(_words(raw))
        lowered = raw.lower().strip()
        if intent.planned_time or intent.day != base_day:
            return "task", 0.995
        if lowered.startswith(("plan ", "strategy ", "roadmap ", "outline ")):
            return "note", 0.965
        if words & GOAL_WORDS:
            return "goal", 0.86
        if words & NOTE_CONTEXT_WORDS:
            return "note", 0.78
        if words & NOTE_WORDS:
            return "note", 0.82
        if words & ACTION_WORDS:
            return "task", 0.94
        return intent.kind, 0.58

    def _memory_score(self, context: list[MemoryItem]) -> tuple[str, float]:
        if not context:
            return "", 0.0
        weights: dict[str, float] = {}
        for item in context[:5]:
            weights[item.kind] = weights.get(item.kind, 0.0) + item.score
        kind = max(weights, key=weights.get)
        confidence = min(0.83, 0.55 + weights[kind] / 5)
        return kind, round(confidence, 3)

    def _model_score(self, prediction) -> tuple[str, float]:
        if prediction is None:
            return "", 0.0
        # Keep the neural model decisive, but leave room for explicit modes,
        # date/time rules, and repeated user memory to override edge cases.
        confidence = 0.62 + min(0.32, prediction.confidence * 0.32)
        return prediction.kind, round(confidence, 3)

    def _tiny_classifier(self) -> TinyIntentClassifier:
        version = self.memory.training_version()
        if self._classifier is None or version != self._classifier_version:
            self._classifier = TinyIntentClassifier(self.memory.training_examples())
            self._classifier_version = version
        return self._classifier


def _words(value: str) -> list[str]:
    return [
        "".join(ch for ch in word.lower() if ch.isalnum())
        for word in value.split()
        if word.strip()
    ]
