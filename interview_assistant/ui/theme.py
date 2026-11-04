from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


BG = "#F4F6F7"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#F8FAFB"
TEXT = "#18212B"
MUTED = "#667085"
BORDER = "#D9E0E5"
ACCENT = "#2F6B58"
ACCENT_HOVER = "#285B4B"
ACCENT_SOFT = "#E8F1EE"
INFO = "#3C6E9F"
INFO_SOFT = "#EAF1F7"
WARNING = "#A8660B"
WARNING_SOFT = "#FBF2E3"
DANGER = "#B42318"
DANGER_SOFT = "#FCEDEA"
HEADER = "#20312B"


APP_STYLESHEET = f"""
* {{
    font-family: "Microsoft YaHei UI";
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QWidget#AppShell {{
    background: {BG};
}}
QFrame#Sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
QFrame#Surface, QFrame[panel="true"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#SectionTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#Muted, QLabel[muted="true"] {{
    color: {MUTED};
}}
QLabel#MetricValue {{
    font-size: 18px;
    font-weight: 600;
}}
QPushButton {{
    min-height: 32px;
    padding: 0 13px;
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton:hover {{
    background: {SURFACE_SOFT};
    border-color: #C6D0D7;
}}
QPushButton:pressed {{
    background: #EDF1F3;
}}
QPushButton:disabled {{
    color: #A0A8AE;
    background: #F2F4F5;
    border-color: #E5E9EC;
}}
QPushButton[variant="primary"] {{
    background: {ACCENT};
    color: white;
    border-color: {ACCENT};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton[variant="danger"] {{
    color: {DANGER};
    border-color: #E7BBB7;
    background: {DANGER_SOFT};
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: transparent;
}}
QPushButton[variant="ghost"]:hover {{
    background: {SURFACE_SOFT};
}}
QPushButton#NavButton {{
    min-height: 40px;
    padding: 0 14px;
    text-align: left;
    border: none;
    background: transparent;
    color: {MUTED};
    font-weight: 500;
}}
QPushButton#NavButton:hover {{
    background: {SURFACE_SOFT};
    color: {TEXT};
}}
QPushButton#NavButton:checked {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: 32px;
    padding: 0 10px;
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: white;
    selection-background-color: {ACCENT_SOFT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    width: 24px;
    border: none;
}}
QComboBox QAbstractItemView {{
    background: white;
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTextEdit, QTextBrowser {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    selection-background-color: #DCE9E4;
}}
QPlainTextEdit {{
    background: #18212B;
    color: #E7ECE9;
    border: 1px solid #2F3B45;
    border-radius: 8px;
    padding: 10px;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
    selection-background-color: #365B4F;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom-color: {ACCENT};
    font-weight: 600;
}}
QTableWidget {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: #EDF0F2;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_SOFT};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 8px;
    font-weight: 600;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #DCE2E5;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: white;
    border: 2px solid {ACCENT};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
}}
QScrollBar:vertical {{
    width: 9px;
    background: transparent;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #C9D1D6;
    min-height: 28px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QToolTip {{
    background: {TEXT};
    color: white;
    border: none;
    padding: 6px 8px;
}}
"""


def apply_theme(app: QApplication):
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_SOFT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_SOFT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    app.setPalette(palette)
    app.setStyleSheet(APP_STYLESHEET)


