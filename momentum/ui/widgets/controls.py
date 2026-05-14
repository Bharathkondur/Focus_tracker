from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QPropertyAnimation, Property, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QWidget


class PillButton(QPushButton):
    def __init__(self, text: str, primary: bool = False, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        if primary:
            self.setObjectName("Primary")


class AnimatedCheck(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, square: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._progress = 1.0 if checked else 0.0
        self._checked = checked
        self.square = square
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.anim = QPropertyAnimation(self, b"progress", self)
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self.anim.stop()
        self.anim.setStartValue(self._progress)
        self.anim.setEndValue(1.0 if checked else 0.0)
        self.anim.start()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.toggled.emit(not self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(4, 4, 22, 22)
        radius = 7 if self.square else 11
        empty = QColor("#101826")
        accent = QColor("#34D399")
        border = QColor("#64748B")
        fill = QColor(
            round(empty.red() + (accent.red() - empty.red()) * self._progress),
            round(empty.green() + (accent.green() - empty.green()) * self._progress),
            round(empty.blue() + (accent.blue() - empty.blue()) * self._progress),
        )
        painter.setPen(QPen(accent if self._progress > 0.2 else border, 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)
        if self._progress > 0.45:
            pen = QPen(QColor("#020617"), 2.8)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(10, 15, 14, 19)
            painter.drawLine(14, 19, 21, 10)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, value: float) -> None:
        self._progress = value
        self.update()

    progress = Property(float, get_progress, set_progress)
