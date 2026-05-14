from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def shadow(widget: QWidget, blur: int = 32, opacity: int = 70) -> None:
    widget.setGraphicsEffect(None)


class Card(QFrame):
    def __init__(self, object_name: str = "Card", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName(object_name)
        shadow(self)


class MetricCard(Card):
    def __init__(self, label: str, value: str = "0%", parent: QWidget | None = None):
        super().__init__("MetricCard", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)
        self.label = QLabel(label)
        self.label.setObjectName("Muted")
        self.value = QLabel(value)
        self.value.setObjectName("Metric")
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class CollapsibleCard(Card):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__("ReflectionCard", parent)
        self.content = QWidget()
        self.content.setMaximumHeight(0)
        self._anim = QPropertyAnimation(self.content, b"maximumHeight", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        self.title = QLabel(title)
        self.title.setObjectName("SectionTitle")
        layout.addWidget(self.title)
        if subtitle:
            label = QLabel(subtitle)
            label.setObjectName("Muted")
            layout.addWidget(label)
        layout.addWidget(self.content)

    def set_expanded(self, expanded: bool) -> None:
        end = self.content.sizeHint().height() if expanded else 0
        self._anim.stop()
        self._anim.setStartValue(self.content.maximumHeight())
        self._anim.setEndValue(end)
        self._anim.start()
