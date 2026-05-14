from __future__ import annotations

from datetime import timedelta

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from momentum.core.analytics import best_weekday, monthly_trend, strongest_and_weakest, weekly_consistency
from momentum.core.dates import today
from momentum.state.store import AppStore
from momentum.ui.widgets.cards import MetricCard


class InsightsView(QWidget):
    def __init__(self, store: AppStore, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        title = QLabel("Insights")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)
        layout.addLayout(self.grid)
        self.cards = {
            "weekly": MetricCard("Weekly consistency", "0%"),
            "strong": MetricCard("Strongest habit", "-"),
            "weak": MetricCard("Weakest habit", "-"),
            "weekday": MetricCard("Best weekday", "-"),
            "trend": MetricCard("Monthly trend", "0"),
        }
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
        for card, (row, col) in zip(self.cards.values(), positions):
            self.grid.addWidget(card, row, col)

    def refresh(self) -> None:
        end = today()
        start = end - timedelta(days=62)
        scores = self.store.repo.day_scores(start, end)
        goals = self.store.repo.active_goals()
        logs = self.store.repo.goal_logs(start, end)
        strong, weak = strongest_and_weakest(goals, logs)
        self.cards["weekly"].set_value(f"{weekly_consistency(scores[-7:])}%")
        self.cards["strong"].set_value(strong)
        self.cards["weak"].set_value(weak)
        self.cards["weekday"].set_value(best_weekday(scores))
        trend = monthly_trend(scores, today().replace(day=1))
        self.cards["trend"].set_value(f"{trend:+d}%")
