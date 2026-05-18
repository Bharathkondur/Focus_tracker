from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


STYLE_DIR = Path(__file__).resolve().parent / "styles"
STYLE_PATH = STYLE_DIR / "dark.qss"
DEFAULT_STYLESHEET = '* {\n    font-family: "Segoe UI Variable", "Segoe UI", "Arial";\n    color: #F8FAFC;\n    outline: 0;\n}\n\nQWidget {\n    background: #0A0F1A;\n}\n\nQLabel {\n    background: transparent;\n}\n\nQMainWindow,\nQWidget#Root {\n    background: #0A0F1A;\n}\n\nQFrame#Sidebar {\n    background: #0D1420;\n    border-right: 1px solid #162235;\n}\n\nQFrame#Card,\nQFrame#MetricCard,\nQFrame#GoalCard,\nQFrame#TaskRow,\nQFrame#ReflectionCard,\nQFrame#InsightCard {\n    background: #101826;\n    border: 1px solid #1D2A3F;\n    border-radius: 18px;\n}\n\nQFrame#GoalCard:hover,\nQFrame#TaskRow:hover {\n    background: #131E2E;\n    border-color: #164A3C;\n}\n\nQLabel#Brand {\n    font-size: 30px;\n    font-weight: 700;\n    letter-spacing: 0;\n}\n\nQLabel#Hero {\n    font-size: 42px;\n    font-weight: 700;\n    letter-spacing: 0;\n}\n\nQLabel#SectionTitle {\n    font-size: 22px;\n    font-weight: 700;\n}\n\nQLabel#Metric {\n    font-size: 34px;\n    font-weight: 700;\n}\n\nQLabel#Muted,\nQLabel#Caption,\nQLabel#Meta {\n    color: #94A3B8;\n}\n\nQLabel#Caption {\n    font-size: 12px;\n    font-weight: 700;\n    letter-spacing: 1px;\n}\n\nQLineEdit,\nQTextEdit {\n    background: #0B1220;\n    border: 1px solid #1D2A3F;\n    border-radius: 14px;\n    padding: 11px 14px;\n    selection-background-color: #065F46;\n}\n\nQLineEdit:focus,\nQTextEdit:focus {\n    border: 1px solid #2F8C69;\n}\n\nQPushButton {\n    background: #162235;\n    border: 1px solid #1D2A3F;\n    border-radius: 14px;\n    padding: 10px 14px;\n    font-weight: 650;\n}\n\nQPushButton:hover {\n    background: #1C2A40;\n    border-color: #164A3C;\n}\n\nQPushButton:pressed {\n    background: #0F3F33;\n}\n\nQPushButton#Primary {\n    background: #34D399;\n    color: #020617;\n    border: none;\n}\n\nQPushButton#Primary:hover {\n    background: #6EE7B7;\n}\n\nQPushButton#Ghost {\n    background: transparent;\n    border: 1px solid #1D2A3F;\n}\n\nQPushButton#MoodButton[active="true"] {\n    background: #34D399;\n    color: #020617;\n}\n\nQCheckBox {\n    spacing: 10px;\n}\n\nQSlider::groove:horizontal {\n    height: 8px;\n    border-radius: 4px;\n    background: #1F2937;\n}\n\nQSlider::sub-page:horizontal {\n    background: #34D399;\n    border-radius: 4px;\n}\n\nQSlider::handle:horizontal {\n    width: 18px;\n    height: 18px;\n    margin: -5px 0;\n    border-radius: 9px;\n    background: #E2E8F0;\n}\n\nQScrollArea {\n    background: transparent;\n    border: none;\n}\n\nQScrollBar:vertical {\n    background: transparent;\n    width: 10px;\n    margin: 4px;\n}\n\nQScrollBar::handle:vertical {\n    background: #263449;\n    border-radius: 5px;\n    min-height: 48px;\n}\n\nQScrollBar::add-line:vertical,\nQScrollBar::sub-line:vertical {\n    height: 0;\n}\n\nQLineEdit QWidget,\nQTextEdit QWidget {\n    background: #0B1220;\n}\n\nQMenu {\n    background: #111827;\n    border: 1px solid #243146;\n    border-radius: 12px;\n    padding: 8px;\n}\n\nQMenu::item {\n    padding: 8px 22px;\n    border-radius: 8px;\n}\n\nQMenu::item:selected {\n    background: #1C2A40;\n}\n'


def load_stylesheet(theme: str = "dark") -> str:
    if STYLE_PATH.exists():
        stylesheet = STYLE_PATH.read_text(encoding="utf-8")
    else:
        stylesheet = DEFAULT_STYLESHEET + """
QToolTip {
    background-color: #101826;
    color: #F8FAFC;
    border: 1px solid #2F8C69;
    border-radius: 8px;
    padding: 8px 10px;
    opacity: 245;
}
"""
    if theme == "light":
        return _lighten(stylesheet)
    return stylesheet


def _lighten(stylesheet: str) -> str:
    replacements = {
        "#0A0F1A": "#F6F8FB",
        "#0D1420": "#EEF2F7",
        "#101826": "#FFFFFF",
        "#0B1220": "#F9FBFE",
        "#08111F": "#FFFFFF",
        "#0A1526": "#F8FAFC",
        "#0F1724": "#FFFFFF",
        "#111827": "#FFFFFF",
        "#12223A": "#E8F2FF",
        "#111E31": "#EDF5FF",
        "#131E2E": "#F3F8FF",
        "#162235": "#E8EEF7",
        "#1C2A40": "#DDE8F7",
        "#0F3F33": "#CDEFE2",
        "#1D2A3F": "#D5DEE9",
        "#162235": "#E8EEF7",
        "#182337": "#DCE5F0",
        "#263449": "#C9D5E3",
        "#243146": "#D5DEE9",
        "#164A3C": "#8ED8BE",
        "#065F46": "#B7EBD8",
        "#2F8C69": "#2F8C69",
        "#34D399": "#10B981",
        "#6EE7B7": "#34D399",
        "#F8FAFC": "#111827",
        "#E2E8F0": "#334155",
        "#94A3B8": "#64748B",
        "#C7D2FE": "#334155",
        "#020617": "#FFFFFF",
        "#FCA5A5": "#B91C1C",
        "#3B1F2A": "#FECACA",
        "#7F1D1D": "#B91C1C",
    }
    for dark, light in replacements.items():
        stylesheet = stylesheet.replace(dark, light)
    return stylesheet


def app_font() -> QFont:
    families = QFontDatabase.families()
    for family in ("Segoe UI Variable", "Segoe UI", "Arial"):
        if family in families:
            return QFont(family, 10)
    return QFont("Arial", 10)
