from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSlider, QTextEdit, QVBoxLayout, QWidget

from momentum.state.store import AppStore
from momentum.ui.widgets.cards import Card
from momentum.ui.widgets.controls import PillButton


class ReflectionView(Card):
    def __init__(self, store: AppStore, parent=None):
        super().__init__("ReflectionCard", parent)
        self.store = store
        self.expanded = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        title = QVBoxLayout()
        heading = QLabel("Reflection")
        heading.setObjectName("SectionTitle")
        sub = QLabel("Capture the day without turning it into paperwork")
        sub.setObjectName("Muted")
        title.addWidget(heading)
        title.addWidget(sub)
        top.addLayout(title)
        top.addStretch()
        self.toggle = QPushButton("Collapse")
        self.toggle.setObjectName("Ghost")
        self.toggle.clicked.connect(self.toggle_details)
        top.addWidget(self.toggle)
        layout.addLayout(top)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        mood_row = QHBoxLayout()
        mood_row.addWidget(QLabel("Mood"))
        self.mood_group = QButtonGroup(self)
        self.mood_group.setExclusive(True)
        for mood in ("Good", "Flat", "Hard"):
            button = QPushButton(mood)
            button.setObjectName("MoodButton")
            button.setCheckable(True)
            self.mood_group.addButton(button)
            mood_row.addWidget(button)
        mood_row.addStretch()
        body.addLayout(mood_row)

        energy_label = QLabel("Energy")
        energy_label.setObjectName("Muted")
        body.addWidget(energy_label)
        self.energy = QSlider(Qt.Horizontal)
        self.energy.setRange(1, 5)
        body.addWidget(self.energy)

        self.short = QTextEdit()
        self.short.setPlaceholderText("Short reflection...")
        self.short.setMaximumHeight(80)
        body.addWidget(self.short)

        self.note = QTextEdit()
        self.note.setPlaceholderText("Notes, observations, anything worth remembering...")
        self.note.setMinimumHeight(120)
        body.addWidget(self.note)

        save = PillButton("Save Reflection", primary=True)
        save.clicked.connect(self.save)
        body.addWidget(save, alignment=Qt.AlignRight)
        layout.addWidget(self.body)

    def refresh(self) -> None:
        reflection = self.store.repo.reflection(self.store.selected_day)
        for button in self.mood_group.buttons():
            active = button.text() == reflection.mood
            button.setChecked(active)
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)
        self.energy.setValue(reflection.energy)
        self.short.setPlainText(reflection.short_reflection)
        self.note.setPlainText(reflection.note)

    def toggle_details(self) -> None:
        self.expanded = not self.expanded
        self.body.setVisible(self.expanded)
        self.toggle.setText("Collapse" if self.expanded else "Expand")

    def save(self) -> None:
        checked = self.mood_group.checkedButton()
        mood = checked.text() if checked else ""
        self.store.save_reflection(
            mood=mood,
            energy=self.energy.value(),
            note=self.note.toPlainText().strip(),
            short_reflection=self.short.toPlainText().strip(),
        )
