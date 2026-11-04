from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QMouseEvent, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models import AppSettings
from . import theme
from .icons import icon
from .widgets import IconButton, StatusDot


class TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_origin = None
        self._window_origin = None
        self._native_move = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._native_move = True
                self._drag_origin = None
                self._window_origin = None
                event.accept()
                return
            self._native_move = False
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            not self._native_move
            and self._drag_origin is not None
            and self._window_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._drag_origin
            self.window().move(self._window_origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_origin = None
        self._window_origin = None
        self._native_move = False
        super().mouseReleaseEvent(event)


class ResizeHandle(QWidget):
    def __init__(self, parent: QWidget, edges: Qt.Edges, cursor: Qt.CursorShape):
        super().__init__(parent)
        self._edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        handle = self.window().windowHandle()
        if handle is not None and handle.startSystemResize(self._edges):
            event.accept()
            return
        event.ignore()


class OverlayWindow(QWidget):
    geometry_changed = Signal(int, int, int, int)
    opacity_changed = Signal(float)
    font_size_changed = Signal(int)
    visible_changed = Signal(bool)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._font_size = settings.overlay_font_size
        self._opacity = settings.overlay_opacity
        self._allow_close = False
        self._last_question = ""
        self._last_answer = ""
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(450)
        self._persist_timer.timeout.connect(self._emit_geometry)
        self._font_preview_timer = QTimer(self)
        self._font_preview_timer.setSingleShot(True)
        self._font_preview_timer.setInterval(2400)
        self._font_preview_timer.timeout.connect(self._hide_font_preview)

        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if settings.overlay_always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("AI 面试助手")
        self.setMinimumSize(560, 360)
        self.resize(settings.overlay_width, settings.overlay_height)
        self.setWindowOpacity(self._opacity)
        self._build_ui()
        self._build_resize_handles()
        self._shortcuts = []
        self._add_shortcut("Ctrl++", lambda: self.change_font_size(2))
        self._add_shortcut("Ctrl+=", lambda: self.change_font_size(2))
        self._add_shortcut("Ctrl+-", lambda: self.change_font_size(-2))
        self._add_shortcut("Esc", self.hide)
        self._place_window()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        self._surface = QFrame()
        self._surface.setObjectName("OverlaySurface")
        self._surface.setStyleSheet(
            "QFrame#OverlaySurface{background:#FFFEFA;border:1px solid #D9E0E5;border-radius:8px;}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(20, 31, 27, 70))
        self._surface.setGraphicsEffect(shadow)
        root_layout.addWidget(self._surface)

        layout = QVBoxLayout(self._surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._titlebar = TitleBar()
        self._titlebar.setObjectName("OverlayHeader")
        self._titlebar.setFixedHeight(62)
        self._titlebar.setStyleSheet(
            "QFrame#OverlayHeader{background:#20312B;border-top-left-radius:7px;border-top-right-radius:7px;}"
        )
        title_layout = QHBoxLayout(self._titlebar)
        title_layout.setContentsMargins(16, 8, 10, 8)
        title_layout.setSpacing(8)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand = QLabel("AI 面试助手")
        brand.setStyleSheet("color:#F7F8F4;font-size:14px;font-weight:600;")
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._meta_label = QLabel("桌面阅读窗")
        self._meta_label.setStyleSheet("color:#B8C5BF;font-size:10px;")
        self._meta_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        brand_box.addWidget(brand)
        brand_box.addWidget(self._meta_label)
        title_layout.addLayout(brand_box)
        title_layout.addStretch(1)

        self._status_dot = StatusDot()
        self._status_label = QLabel("准备就绪")
        self._status_label.setStyleSheet("color:#D8E0DC;font-size:11px;")
        self._status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_layout.addWidget(self._status_dot)
        title_layout.addWidget(self._status_label)
        title_layout.addSpacing(12)

        self._font_title = QLabel("字号")
        self._font_title.setStyleSheet("color:#B8C5BF;font-size:10px;")
        self._font_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._font_minus_button = IconButton("minus", "减小字号（每次 2 px）", icon_size=16)
        self._font_minus_button.clicked.connect(lambda: self.change_font_size(-2))
        self._font_label = QLabel(str(self._font_size))
        self._font_label.setFixedWidth(24)
        self._font_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._font_label.setStyleSheet("color:#DCE5E1;font-size:11px;font-weight:600;")
        self._font_plus_button = IconButton("plus", "增大字号（每次 2 px）", icon_size=16)
        self._font_plus_button.clicked.connect(lambda: self.change_font_size(2))

        self._pin_button = IconButton("pin", "切换置顶", icon_size=16)
        self._pin_button.setCheckable(True)
        self._pin_button.setChecked(self._settings.overlay_always_on_top)
        self._pin_button.clicked.connect(self._toggle_topmost)

        self._opacity_button = IconButton("opacity", "调整窗口不透明度", icon_size=18)
        self._opacity_button.setCheckable(True)
        self._opacity_button.clicked.connect(self._toggle_opacity_panel)

        self._close_button = IconButton("x", "关闭悬浮窗", icon_size=17)
        self._close_button.clicked.connect(self.hide)

        for button in (
            self._font_minus_button,
            self._font_plus_button,
            self._pin_button,
            self._opacity_button,
            self._close_button,
        ):
            button.setStyleSheet(
                "QPushButton{border-color:transparent;background:transparent;border-radius:6px;}"
                "QPushButton:hover{background:#30463E;}"
                "QPushButton:checked{background:#3A6757;}"
            )

        title_layout.addWidget(self._font_title)
        title_layout.addWidget(self._font_minus_button)
        title_layout.addWidget(self._font_label)
        title_layout.addWidget(self._font_plus_button)
        title_layout.addWidget(self._pin_button)
        title_layout.addWidget(self._opacity_button)
        title_layout.addWidget(self._close_button)
        layout.addWidget(self._titlebar)

        self._font_preview_panel = QFrame(self._surface)
        self._font_preview_panel.setObjectName("FontPreviewPanel")
        self._font_preview_panel.setStyleSheet(
            "QFrame#FontPreviewPanel{background:#FFFFFF;border:1px solid #D9E0E5;border-radius:6px;}"
        )
        font_preview_layout = QVBoxLayout(self._font_preview_panel)
        font_preview_layout.setContentsMargins(14, 8, 14, 10)
        font_preview_layout.setSpacing(3)
        self._font_preview_title = QLabel()
        self._font_preview_title.setStyleSheet("color:#667085;font-size:10px;")
        self._font_preview_sample = QLabel("\u8fd9\u662f\u56de\u7b54\u6587\u5b57\u7684\u5b9e\u9645\u663e\u793a\u6548\u679c\u3002")
        self._font_preview_sample.setWordWrap(True)
        self._font_preview_sample.setStyleSheet("color:#18212B;")
        font_preview_layout.addWidget(self._font_preview_title)
        font_preview_layout.addWidget(self._font_preview_sample, 1)
        self._font_preview_panel.hide()

        self._opacity_panel = QFrame(self._surface)
        self._opacity_panel.setObjectName("OpacityPanel")
        self._opacity_panel.setStyleSheet(
            "QFrame#OpacityPanel{background:#FFFFFF;border:1px solid #D9E0E5;border-radius:6px;}"
            "QLabel{color:#52616A;font-size:11px;}"
        )
        opacity_layout = QHBoxLayout(self._opacity_panel)
        opacity_layout.setContentsMargins(16, 8, 16, 8)
        opacity_layout.setSpacing(10)
        opacity_layout.addWidget(QLabel("窗口不透明度"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(65, 100)
        self._opacity_slider.setSingleStep(1)
        self._opacity_slider.setPageStep(5)
        self._opacity_slider.setValue(round(self._opacity * 100))
        self._opacity_slider.valueChanged.connect(self._apply_opacity)
        opacity_layout.addWidget(self._opacity_slider, 1)
        self._opacity_value = QLabel(f"{round(self._opacity * 100)}%")
        self._opacity_value.setFixedWidth(38)
        self._opacity_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        reset = QPushButton("恢复默认")
        reset.setProperty("variant", "ghost")
        reset.setFixedHeight(26)
        reset.clicked.connect(lambda: self._opacity_slider.setValue(96))
        opacity_layout.addWidget(self._opacity_value)
        opacity_layout.addWidget(reset)
        self._opacity_panel.setFixedHeight(48)
        self._opacity_panel.hide()

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(6)
        self._splitter.setStyleSheet("QSplitter::handle{background:#E8ECEE;}")

        self._question_panel = QFrame()
        self._question_panel.setStyleSheet("background:#F3E8D7;")
        question_layout = QVBoxLayout(self._question_panel)
        question_layout.setContentsMargins(18, 11, 14, 12)
        question_layout.setSpacing(7)
        question_header = QHBoxLayout()
        question_title = QLabel("面试官提问")
        question_title.setStyleSheet("color:#A8660B;font-size:11px;font-weight:600;")
        self._collapse_button = IconButton("chevron-down", "折叠问题区域", icon_size=15, color="#A8660B")
        self._collapse_button.setFixedSize(26, 26)
        self._collapse_button.clicked.connect(self._toggle_question)
        question_header.addWidget(question_title)
        question_header.addStretch(1)
        question_header.addWidget(self._collapse_button)
        question_layout.addLayout(question_header)
        self._question_text = QTextEdit()
        self._question_text.setReadOnly(True)
        self._question_text.setPlaceholderText("等待面试官提问...")
        self._question_text.setStyleSheet("QTextEdit{background:transparent;border:none;padding:0;color:#18212B;}")
        question_layout.addWidget(self._question_text, 1)
        self._splitter.addWidget(self._question_panel)

        self._answer_panel = QFrame()
        self._answer_panel.setStyleSheet("background:#FFFEFA;")
        answer_layout = QVBoxLayout(self._answer_panel)
        answer_layout.setContentsMargins(18, 13, 14, 12)
        answer_layout.setSpacing(7)
        answer_title = QLabel("回答建议")
        answer_title.setStyleSheet(f"color:{theme.ACCENT};font-size:12px;font-weight:600;")
        answer_layout.addWidget(answer_title)
        self._answer_text = QTextEdit()
        self._answer_text.setReadOnly(True)
        self._answer_text.setPlaceholderText("识别到问题后，回答会在这里实时生成。")
        self._answer_text.setStyleSheet("QTextEdit{background:transparent;border:none;padding:0;color:#18212B;}")
        answer_layout.addWidget(self._answer_text, 1)
        self._splitter.addWidget(self._answer_panel)
        self._splitter.setSizes([190, 330])
        layout.addWidget(self._splitter, 1)

        footer = QFrame()
        footer.setStyleSheet("background:#ECE8DF;border-bottom-left-radius:7px;border-bottom-right-radius:7px;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 6, 14, 6)
        self._sync_label = QLabel("等待问答")
        self._sync_label.setStyleSheet("color:#667085;font-size:10px;")
        self._copy_button = QPushButton("  复制回答")
        self._copy_button.setIcon(icon("copy", theme.TEXT, 16))
        self._copy_button.setProperty("variant", "ghost")
        self._copy_button.setFixedHeight(28)
        self._copy_button.clicked.connect(self._copy_answer)
        footer_layout.addWidget(self._sync_label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._copy_button)
        layout.addWidget(footer)

        self._apply_editor_font()

    def _add_shortcut(self, sequence: str, callback):
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)
        self._shortcuts.append(shortcut)

    def _build_resize_handles(self):
        self._resize_handles = [
            ResizeHandle(self, Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
            ResizeHandle(self, Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
            ResizeHandle(self, Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
            ResizeHandle(self, Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
            ResizeHandle(self, Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeFDiagCursor),
            ResizeHandle(self, Qt.Edge.RightEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeFDiagCursor),
            ResizeHandle(self, Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.CursorShape.SizeBDiagCursor),
            ResizeHandle(self, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge, Qt.CursorShape.SizeBDiagCursor),
        ]
        for handle in self._resize_handles:
            handle.show()
            handle.raise_()

    def _layout_resize_handles(self):
        if not hasattr(self, "_resize_handles"):
            return
        rect = self._surface.geometry()
        grip = 10
        inset = 2
        geometries = [
            QRect(rect.left() - inset, rect.top() + grip, 8, max(20, rect.height() - 2 * grip)),
            QRect(rect.right() - inset - 4, rect.top() + grip, 8, max(20, rect.height() - 2 * grip)),
            QRect(rect.left() + grip, rect.top() - inset, max(20, rect.width() - 2 * grip), 8),
            QRect(rect.left() + grip, rect.bottom() - inset - 4, max(20, rect.width() - 2 * grip), 8),
            QRect(rect.left() - inset, rect.top() - inset, grip + 4, grip + 4),
            QRect(rect.right() - inset - 3, rect.bottom() - inset - 3, grip + 4, grip + 4),
            QRect(rect.right() - inset - 3, rect.top() - inset, grip + 4, grip + 4),
            QRect(rect.left() - inset, rect.bottom() - inset - 3, grip + 4, grip + 4),
        ]
        for handle, geometry in zip(self._resize_handles, geometries):
            handle.setGeometry(geometry)
            handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._meta_label.setVisible(self.width() >= 660)
        self._position_opacity_panel()
        self._position_font_preview()
        QTimer.singleShot(0, self._layout_resize_handles)
        if self.isVisible():
            self._persist_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self._persist_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.visible_changed.emit(True)
        QTimer.singleShot(0, self._layout_resize_handles)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visible_changed.emit(False)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()

    def shutdown_ui(self):
        self._allow_close = True
        self.close()

    def _place_window(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = min(self._settings.overlay_width, max(560, available.width() - 40))
        height = min(self._settings.overlay_height, max(360, available.height() - 60))
        if self._settings.overlay_x is not None and self._settings.overlay_y is not None:
            x = max(available.left(), min(self._settings.overlay_x, available.right() - width))
            y = max(available.top(), min(self._settings.overlay_y, available.bottom() - height))
        else:
            x = available.right() - width - 28
            y = available.top() + max(40, (available.height() - height) // 2 - 24)
        self.setGeometry(x, y, width, height)

    def _emit_geometry(self):
        if self.isVisible():
            geometry = self.geometry()
            self.geometry_changed.emit(geometry.x(), geometry.y(), geometry.width(), geometry.height())

    def _apply_editor_font(self):
        question_size = max(15, self._font_size - 3)
        self._answer_text.setStyleSheet(
            "QTextEdit{background:transparent;border:none;padding:0;"
            f"color:#18212B;font-size:{self._font_size}px;}}"
        )
        self._question_text.setStyleSheet(
            "QTextEdit{background:transparent;border:none;padding:0;"
            f"color:#18212B;font-size:{question_size}px;}}"
        )
        self._font_label.setText(str(self._font_size))

    def change_font_size(self, delta: int):
        new_size = max(16, min(32, self._font_size + delta))
        if new_size == self._font_size:
            return
        self._font_size = new_size
        self._apply_editor_font()
        self._show_font_preview()
        self.font_size_changed.emit(self._font_size)

    def _position_font_preview(self):
        if not hasattr(self, "_font_preview_panel"):
            return
        width = max(260, self._surface.width() - 40)
        height = max(64, min(116, 30 + self._font_size * 2))
        top = self._titlebar.geometry().bottom() + 8
        self._font_preview_panel.setGeometry(20, top, width, height)

    def _show_font_preview(self):
        self._font_preview_title.setText(f"\u5b57\u53f7\u9884\u89c8 \u00b7 {self._font_size} px")
        self._font_preview_sample.setStyleSheet(
            f"color:#18212B;font-size:{self._font_size}px;"
        )
        self._position_font_preview()
        self._font_preview_panel.show()
        self._font_preview_panel.raise_()
        self._font_preview_timer.start()

    def _hide_font_preview(self):
        if hasattr(self, "_font_preview_panel"):
            self._font_preview_panel.hide()

    def _toggle_topmost(self, checked: bool):
        self._settings.overlay_always_on_top = checked
        geometry = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.setGeometry(geometry)
        self.show()
        self.raise_()

    def _position_opacity_panel(self):
        if not hasattr(self, "_opacity_panel") or not hasattr(self, "_opacity_button"):
            return
        surface_width = self._surface.width()
        surface_height = self._surface.height()
        panel_width = min(420, max(320, surface_width - 24))
        panel_height = self._opacity_panel.height() or 48
        button_pos = self._opacity_button.mapTo(
            self._surface, QPoint(0, self._opacity_button.height())
        )
        x = button_pos.x() - panel_width + self._opacity_button.width()
        x = max(12, min(x, surface_width - panel_width - 12))
        y = button_pos.y() + 6
        y = min(y, surface_height - panel_height - 12)
        self._opacity_panel.setGeometry(x, y, panel_width, panel_height)

    def _toggle_opacity_panel(self, checked: bool | None = None):
        visible = not self._opacity_panel.isVisible()
        if visible:
            self._position_opacity_panel()
        self._opacity_panel.setVisible(visible)
        self._opacity_button.setChecked(visible)
        if visible:
            self._opacity_panel.raise_()
            self._opacity_panel.update()

    def _apply_opacity(self, value: int):
        self._opacity = value / 100.0
        self._opacity_value.setText(f"{value}%")
        self.setWindowOpacity(self._opacity)
        self.opacity_changed.emit(self._opacity)

    def _toggle_question(self):
        visible = not self._question_text.isVisible()
        self._question_text.setVisible(visible)
        self._collapse_button.setIcon(icon("chevron-up" if visible else "chevron-down", "#A8660B", 15))

    def _copy_answer(self):
        if not self._last_answer:
            return
        QApplication.clipboard().setText(self._last_answer)
        self._sync_label.setText("回答已复制")
        QTimer.singleShot(1300, lambda: self._sync_label.setText(self._last_sync_text()))

    def _last_sync_text(self) -> str:
        return f"最近同步 {self._last_sync}" if hasattr(self, "_last_sync") else "等待问答"

    def set_meta(self, value: str):
        self._meta_label.setText(value)

    def set_status(self, text_value: str, kind: str = "info"):
        colors = {"info": "#78D0AA", "working": "#E3A449", "ready": "#78D0AA", "error": "#E4776A"}
        self._status_dot.set_color(colors.get(kind, "#78D0AA"))
        self._status_label.setText(text_value)

    def begin_question(self):
        self._question_text.clear()
        self._answer_text.clear()
        self._last_question = ""
        self._last_answer = ""

    def append_question_partial(self, text_value: str):
        self._last_question += text_value
        self._question_text.setPlainText(self._last_question)

    def set_question(self, question: str):
        self._last_question = question
        self._question_text.setPlainText(question)

    def begin_answer(self):
        self._answer_text.clear()
        self._last_answer = ""

    def append_answer(self, delta: str):
        self._answer_text.moveCursor(QTextCursor.MoveOperation.End)
        self._answer_text.insertPlainText(delta)
        self._last_answer += delta
        self._last_sync = datetime.now().strftime("%H:%M:%S")
        self._sync_label.setText(self._last_sync_text())

    def set_answer(self, answer: str):
        self._last_answer = answer
        self._answer_text.setPlainText(answer)
        self._last_sync = datetime.now().strftime("%H:%M:%S")
        self._sync_label.setText(self._last_sync_text())

    def clear_content(self):
        self._last_question = ""
        self._last_answer = ""
        self._question_text.clear()
        self._answer_text.clear()
        self._sync_label.setText("等待问答")
        self.set_status("已清空", "info")

    def apply_settings(self, settings: AppSettings):
        self._settings = settings
        self._font_size = settings.overlay_font_size
        self._opacity = settings.overlay_opacity
        self.setWindowOpacity(self._opacity)
        self._opacity_slider.blockSignals(True)
        self._opacity_slider.setValue(round(self._opacity * 100))
        self._opacity_value.setText(f"{round(self._opacity * 100)}%")
        self._opacity_slider.blockSignals(False)
        self._pin_button.setChecked(settings.overlay_always_on_top)
        self._apply_editor_font()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
