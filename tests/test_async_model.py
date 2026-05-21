from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from momentum.capture.local_model import ModelPrediction
from momentum.ui.capture.async_model import AsyncIntentPredictor, AsyncIntentResult


class FakeModel:
    def __init__(self, prediction=None, should_raise: bool = False):
        self.prediction = prediction
        self.should_raise = should_raise
        self.calls: list[str] = []

    def predict(self, text: str):
        self.calls.append(text)
        if self.should_raise:
            raise RuntimeError("boom")
        return self.prediction


def _wait_for_prediction(predictor: AsyncIntentPredictor, text: str) -> AsyncIntentResult:
    app = QApplication.instance() or QApplication([])
    result: list[AsyncIntentResult] = []
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    predictor.finished.connect(lambda value: (result.append(value), loop.quit()))

    request_id = predictor.predict(text)
    timer.start(2000)
    loop.exec()
    app.processEvents()

    assert result, "async predictor did not emit a result"
    assert result[0].request_id == request_id
    return result[0]


def test_async_intent_predictor_emits_prediction_result() -> None:
    prediction = ModelPrediction(
        kind="task",
        confidence=0.91,
        scores={"task": 0.91, "goal": 0.05, "note": 0.04},
        status="fake",
    )
    model = FakeModel(prediction)
    predictor = AsyncIntentPredictor(model)

    result = _wait_for_prediction(predictor, "send resume")

    assert model.calls == ["send resume"]
    assert result.text == "send resume"
    assert result.prediction == prediction


def test_async_intent_predictor_emits_none_when_model_raises() -> None:
    model = FakeModel(should_raise=True)
    predictor = AsyncIntentPredictor(model)

    result = _wait_for_prediction(predictor, "send resume")

    assert model.calls == ["send resume"]
    assert result.text == "send resume"
    assert result.prediction is None
