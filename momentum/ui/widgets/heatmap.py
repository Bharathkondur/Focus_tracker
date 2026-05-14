from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget


@dataclass(slots=True)
class HeatCell:
    day: date
    value: int
    status: str = ""
    note: str = ""


class HeatmapWidget(QWidget):
    day_clicked = Signal(object)
    day_context_requested = Signal(object, QPoint)

    def __init__(self, days: int = 365, columns: int = 53, compact: bool = False, parent=None):
        super().__init__(parent)
        self.days = days
        self.columns = columns
        self.compact = compact
        self.cells: dict[date, HeatCell] = {}
        self.rects: list[tuple[QRectF, HeatCell]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(96 if compact else 142)

    def set_cells(self, cells: list[HeatCell]) -> None:
        self.cells = {cell.day: cell for cell in cells}
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self.rects.clear()
        if self.days <= 0:
            return
        rows = max(1, (self.days + self.columns - 1) // self.columns)
        gap = 4 if self.compact else 5
        width = self.width()
        height = self.height()
        cell = min((width - gap * (self.columns - 1)) / self.columns, (height - gap * (rows - 1)) / rows)
        cell = max(5, min(cell, 16 if self.compact else 18))
        start_x = 0
        start_y = (height - (rows * cell + (rows - 1) * gap)) / 2
        start = date.today() - timedelta(days=self.days - 1)
        for index in range(self.days):
            day = start + timedelta(days=index)
            col = index % self.columns
            row = index // self.columns
            rect = QRectF(start_x + col * (cell + gap), start_y + row * (cell + gap), cell, cell)
            cell_data = self.cells.get(day, HeatCell(day=day, value=0))
            painter.setPen(QPen(self.color_for(cell_data), 1))
            painter.setBrush(self.color_for(cell_data))
            painter.drawRoundedRect(rect, 3, 3)
            self.rects.append((rect, cell_data))

    def mouseMoveEvent(self, event) -> None:
        item = self.cell_at(event.position())
        if item:
            QToolTip.showText(event.globalPosition().toPoint(), self.tooltip_text(item), self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        item = self.cell_at(event.position())
        if item and event.button() == Qt.LeftButton:
            self.day_clicked.emit(item.day)
        elif item and event.button() == Qt.RightButton:
            self.day_context_requested.emit(item.day, event.globalPosition().toPoint())
        super().mouseReleaseEvent(event)

    def cell_at(self, pos) -> HeatCell | None:
        point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        for rect, cell in self.rects:
            if rect.contains(point):
                return cell
        return None

    def color_for(self, cell: HeatCell) -> QColor:
        if cell.status == "vacation":
            return QColor("#1E3A5F")
        if cell.status == "skipped":
            return QColor("#2A3548")
        value = max(0, min(100, cell.value))
        if value >= 90:
            return QColor("#34D399")
        if value >= 65:
            return QColor("#059669")
        if value >= 35:
            return QColor("#065F46")
        if value > 0:
            return QColor("#0F3F33")
        return QColor("#1F2937")

    def tooltip_text(self, cell: HeatCell) -> str:
        day = cell.day.strftime("%A, %b %d, %Y")
        if cell.status:
            detail = cell.status.replace("_", " ").title()
        else:
            detail = f"{cell.value}% complete"
        if cell.note:
            return f"{day}\n{detail}\n{cell.note}"
        return f"{day}\n{detail}"


class GoalHeatmap(HeatmapWidget):
    def __init__(self, parent=None):
        super().__init__(days=21, columns=7, compact=True, parent=parent)
