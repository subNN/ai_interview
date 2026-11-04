from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .icons import icon


class IconButton(QPushButton):
    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        parent: QWidget | None = None,
        icon_size: int = 18,
        color: str = theme.MUTED,
    ):
        super().__init__(parent)
        self.setIcon(icon(icon_name, color, icon_size))
        self.setIconSize(QSize(icon_size, icon_size))
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFixedSize(34, 34)
        self.setProperty("variant", "ghost")


class StatusDot(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor("#9AA4AA")
        self.setFixedSize(12, 12)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(2, 2, 8, 8)


class Metric(QFrame):
    def __init__(self, title: str, value: str = "—", parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("panel", True)
        self.setMinimumHeight(74)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setProperty("muted", True)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        layout.addWidget(label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class PageHeading(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Muted")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)


class LogView(QTextEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setObjectName("LogConsole")
        self.document().setMaximumBlockCount(2500)
        self.setStyleSheet(
            "QTextEdit { background:#18212B; color:#E7ECE9; border:1px solid #2F3B45; "
            'font-family:"Cascadia Mono","Consolas"; font-size:12px; padding:10px; }'
        )
        self._auto_follow = True

    def set_auto_follow(self, enabled: bool):
        self._auto_follow = enabled

    def append_record(self, record: dict):
        level = record.get("level", "INFO")
        color = {
            "ERROR": "#FF8A80",
            "WARNING": "#F2BE72",
            "DEBUG": "#9EAAB3",
            "INFO": "#DDE8E3",
        }.get(level, "#DDE8E3")
        timestamp = record.get("timestamp") or datetime.now().strftime("%H:%M:%S")
        source = record.get("source", "app")
        message = (
            str(record.get("message", ""))
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.append(
            f'<span style="color:#82919A">{timestamp}</span> '
            f'<span style="color:{color}">{level:7s}</span> '
            f'<span style="color:#87AFA0">{source}</span> '
            f'<span style="color:#E7ECE9">{message}</span>'
        )
        if self._auto_follow and at_bottom:
            bar.setValue(bar.maximum())


def _install_step_buttons(widget):
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
    editor = widget.lineEdit()
    if editor is not None:
        editor.setTextMargins(10, 0, 32, 0)
    widget._step_up = QToolButton(widget)
    widget._step_up.setText("\u2227")
    widget._step_up.setToolTip("\u589e\u52a0")
    widget._step_up.clicked.connect(widget.stepUp)
    widget._step_down = QToolButton(widget)
    widget._step_down.setText("\u2228")
    widget._step_down.setToolTip("\u51cf\u5c11")
    widget._step_down.clicked.connect(widget.stepDown)
    for button in (widget._step_up, widget._step_down):
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            "QToolButton{border:none;background:#FFFFFF;color:#52616A;"
            "font-size:13px;font-weight:600;padding:0;}"
            "QToolButton:hover{background:#EAF1F7;color:#2F6B58;}"
        )
        button.show()
    _position_step_buttons(widget)


def _position_step_buttons(widget):
    if not hasattr(widget, "_step_up"):
        return
    width = 24
    half = max(14, (widget.height() - 2) // 2)
    x = widget.width() - width - 1
    widget._step_up.setGeometry(x, 1, width, half)
    widget._step_down.setGeometry(x, 1 + half, width, half)
    widget._step_up.raise_()
    widget._step_down.raise_()


class SpinBox(QSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        _install_step_buttons(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _position_step_buttons(self)


class DoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        _install_step_buttons(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _position_step_buttons(self)


class SecretLineEdit(QWidget):
    text_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        from PySide6.QtWidgets import QLineEdit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line_edit = QLineEdit()
        self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.line_edit.textChanged.connect(self.text_changed)
        self.toggle_button = IconButton("eye-off", "显示密钥")
        self.toggle_button.setCheckable(True)
        self.toggle_button.toggled.connect(self._toggle_visibility)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.toggle_button)

    def _toggle_visibility(self, visible: bool):
        from PySide6.QtWidgets import QLineEdit

        self.line_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.toggle_button.setIcon(icon("eye" if visible else "eye-off", theme.MUTED, 18))
        self.toggle_button.setToolTip("隐藏密钥" if visible else "显示密钥")

    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, value: str):
        self.line_edit.setText(value)


def stretch_label(text_value: str, muted: bool = False) -> QLabel:
    label = QLabel(text_value)
    label.setWordWrap(True)
    if muted:
        label.setProperty("muted", True)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return label



