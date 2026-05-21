from __future__ import annotations

from dataclasses import dataclass
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from momentum.capture.local_model import LocalIntentModel, ModelPrediction


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AsyncIntentResult:
    request_id: int
    text: str
    prediction: ModelPrediction | None


class _PredictionSignals(QObject):
    finished = Signal(object)


class _PredictionWorker(QRunnable):
    def __init__(self, model: LocalIntentModel, request_id: int, text: str):
        super().__init__()
        self.model = model
        self.request_id = request_id
        self.text = text
        self.signals = _PredictionSignals()

    @Slot()
    def run(self) -> None:
        prediction: ModelPrediction | None = None
        try:
            prediction = self.model.predict(self.text)
        except Exception:
            logger.exception("Background local intent prediction failed")
        self.signals.finished.emit(AsyncIntentResult(self.request_id, self.text, prediction))


class AsyncIntentPredictor(QObject):
    finished = Signal(object)

    def __init__(self, model: LocalIntentModel):
        super().__init__()
        self.model = model
        self.pool = QThreadPool.globalInstance()
        self._request_id = 0
        self._workers: dict[int, _PredictionWorker] = {}

    def predict(self, text: str) -> int:
        self._request_id += 1
        request_id = self._request_id
        worker = _PredictionWorker(self.model, request_id, text)
        self._workers[request_id] = worker
        worker.signals.finished.connect(self._finish)
        self.pool.start(worker)
        return request_id

    def _finish(self, result: AsyncIntentResult) -> None:
        self._workers.pop(result.request_id, None)
        self.finished.emit(result)
