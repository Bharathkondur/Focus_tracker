from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QPushButton, QVBoxLayout

from momentum.core.analytics import best_weekday, weekly_consistency
from momentum.core.dates import today
from momentum.state.store import AppStore
from momentum.ui.widgets.cards import MetricCard
from momentum.ui.widgets.heatmap import HeatCell, HeatmapWidget
from momentum.ui.widgets.settings import SettingsDialog


class Sidebar(QFrame):
    def __init__(self, store: AppStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("Sidebar")
        self.setFixedWidth(312)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(22)

        brand = QLabel("Momentum")
        brand.setObjectName("Brand")
        subtitle = QLabel("Build consistency quietly.")
        subtitle.setObjectName("Muted")
        layout.addWidget(brand)
        layout.addWidget(subtitle)

        cap = QLabel("YEARLY CONSISTENCY")
        cap.setObjectName("Caption")
        layout.addWidget(cap)
        self.heatmap = HeatmapWidget(days=365, columns=26, compact=True)
        self.heatmap.day_clicked.connect(self.store.set_day)
        self.heatmap.day_context_requested.connect(self.open_day_menu)
        layout.addWidget(self.heatmap)

        self.today_card = MetricCard("Today", "0%")
        self.week_card = MetricCard("Weekly consistency", "0%")
        layout.addWidget(self.today_card)
        layout.addWidget(self.week_card)

        insight_label = QLabel("INSIGHTS")
        insight_label.setObjectName("Caption")
        layout.addWidget(insight_label)
        self.best = QLabel("-")
        self.best.setObjectName("Muted")
        self.best.setWordWrap(True)
        layout.addWidget(self.best)
        layout.addStretch()

        settings = QPushButton("Settings")
        settings.setObjectName("Ghost")
        settings.clicked.connect(self.open_settings)
        layout.addWidget(settings)

    def refresh(self) -> None:
        end = today()
        start = end - timedelta(days=364)
        scores = self.store.repo.day_scores(start, end)
        self.heatmap.set_cells([
            HeatCell(score.day, score.percent, "vacation" if score.vacation else "")
            for score in scores
        ])
        selected = self.store.repo.day_scores(self.store.selected_day, self.store.selected_day)[0]
        self.today_card.set_value(f"{selected.percent}%")
        self.week_card.set_value(f"{weekly_consistency(scores[-7:])}%")
        self.best.setText(f"Best weekday: {best_weekday(scores)}")

    def open_day_menu(self, day, point: QPoint) -> None:
        self.store.set_day(day)
        menu = QMenu(self)
        menu.addAction("Open day", lambda: self.store.set_day(day))
        menu.addAction("Mark vacation day", lambda: self.store.mark_vacation_day(True))
        menu.addAction("Clear vacation mark", lambda: self.store.mark_vacation_day(False))
        menu.exec(point)

    def open_settings(self) -> None:
        SettingsDialog(self).exec()
