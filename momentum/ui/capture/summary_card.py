from __future__ import annotations

from PySide6.QtWidgets import QDateEdit, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from momentum.capture.summary import build_summary, preset_range
from momentum.ui.capture.accessibility import _accessible
from momentum.ui.capture.utils import _clear_layout, _from_qdate, _to_qdate
from momentum.ui.widgets.cards import Card
class SummaryCard(Card):
    def __init__(self, window: CaptureWindow):
        super().__init__("InsightCard")
        self.window = window
        self.current_preset = "7d"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Momentum Summary")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.buttons = {}
        for label, preset in (("7 Days", "7d"), ("1 Month", "30d"), ("1 Year", "1y")):
            button = QPushButton(label)
            button.setObjectName("Primary" if preset == self.current_preset else "Ghost")
            _accessible(button, f"Show {label} summary")
            button.clicked.connect(lambda _checked=False, value=preset: self.set_preset(value))
            self.buttons[preset] = button
            header.addWidget(button)
        layout.addLayout(header)

        custom = QHBoxLayout()
        custom.addWidget(QLabel("From"))
        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        _accessible(self.start_edit, "Summary start date")
        custom.addWidget(self.start_edit)
        custom.addWidget(QLabel("To"))
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        _accessible(self.end_edit, "Summary end date")
        custom.addWidget(self.end_edit)
        apply_button = QPushButton("Apply")
        _accessible(apply_button, "Apply custom summary date range")
        apply_button.clicked.connect(self.apply_custom)
        custom.addWidget(apply_button)
        layout.addLayout(custom)

        self.range_label = QLabel("")
        self.range_label.setObjectName("Caption")
        layout.addWidget(self.range_label)

        self.metrics = QGridLayout()
        self.metrics.setHorizontalSpacing(10)
        self.metrics.setVerticalSpacing(10)
        self.metric_cards: list[MetricTile] = []
        for index in range(6):
            tile = MetricTile()
            self.metric_cards.append(tile)
            self.metrics.addWidget(tile, index // 3, index % 3)
        layout.addLayout(self.metrics)

        lists = QHBoxLayout()
        lists.setSpacing(12)
        self.bullets = SimpleTextPanel("What Happened")
        self.focus = SimpleTextPanel("Suggested Focus")
        lists.addWidget(self.bullets, 1)
        lists.addWidget(self.focus, 1)
        layout.addLayout(lists)

        self.set_preset("7d")

    def set_preset(self, preset: str) -> None:
        self.current_preset = preset
        for key, button in self.buttons.items():
            button.setObjectName("Primary" if key == preset else "Ghost")
            button.style().unpolish(button)
            button.style().polish(button)
        start, end = preset_range(preset)
        self.start_edit.setDate(_to_qdate(start))
        self.end_edit.setDate(_to_qdate(end))
        self.refresh()

    def apply_custom(self) -> None:
        self.current_preset = "custom"
        for button in self.buttons.values():
            button.setObjectName("Ghost")
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh()

    def refresh(self) -> None:
        start = _from_qdate(self.start_edit.date())
        end = _from_qdate(self.end_edit.date())
        summary = build_summary(self.window.repo, start, end)
        self.range_label.setText(summary.title)
        for tile, metric in zip(self.metric_cards, summary.metrics):
            tile.set_metric(metric.label, metric.value, metric.detail)
        self.bullets.clear()
        for item in summary.bullets:
            self.bullets.add(item)
        self.focus.clear()
        for item in summary.focus:
            self.focus.add(item)

class MetricTile(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("MetricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.label = QLabel("")
        self.label.setObjectName("Muted")
        self.value = QLabel("")
        self.value.setObjectName("Metric")
        self.detail = QLabel("")
        self.detail.setObjectName("Caption")
        self.detail.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_metric(self, label: str, value: str, detail: str) -> None:
        self.label.setText(label)
        self.value.setText(value)
        self.detail.setText(detail)

class SimpleTextPanel(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("Caption")
        layout.addWidget(label)
        self.items = QVBoxLayout()
        self.items.setSpacing(6)
        layout.addLayout(self.items)
        layout.addStretch()

    def add(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        self.items.addWidget(label)

    def clear(self) -> None:
        while self.items.count():
            item = self.items.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
