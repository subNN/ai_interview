from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..history import HistoryStore
from ..models import AppSettings, Secrets
from . import theme
from .icons import icon
from .pages import HistoryPage, LivePage, LogsPage, SettingsPage
from .widgets import StatusDot


class MainWindow(QMainWindow):
    start_requested = Signal()
    stop_requested = Signal()
    manual_requested = Signal()
    cancel_requested = Signal()
    clear_requested = Signal()
    overlay_requested = Signal()
    settings_saved = Signal(object, object)
    hide_to_tray = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        settings: AppSettings,
        secrets: Secrets,
        history: HistoryStore,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._secrets = secrets
        self._history = history
        self._force_close = False
        self._session_active = False
        self.setWindowTitle("AI 面试助手")
        self.setMinimumSize(920, 640)
        self.resize(1120, 760)
        self._build_ui()
        self._build_timer()

    def _build_ui(self):
        shell = QWidget()
        shell.setObjectName("AppShell")
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 20, 18, 18)
        sidebar_layout.setSpacing(6)

        brand = QHBoxLayout()
        logo = QLabel("AI")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(34, 34)
        logo.setStyleSheet(
            f"background:{theme.ACCENT};color:white;border-radius:7px;"
            "font-size:12px;font-weight:700;"
        )
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel("面试助手")
        name.setStyleSheet("font-size:15px;font-weight:600;")
        version = QLabel("Desktop 1.1")
        version.setProperty("muted", True)
        version.setStyleSheet("font-size:10px;")
        brand_text.addWidget(name)
        brand_text.addWidget(version)
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        sidebar_layout.addLayout(brand)
        sidebar_layout.addSpacing(24)

        nav_label = QLabel("工作区")
        nav_label.setProperty("muted", True)
        nav_label.setStyleSheet("font-size:10px;font-weight:600;")
        sidebar_layout.addWidget(nav_label)
        sidebar_layout.addSpacing(2)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [
            ("实时面试", "activity", 0),
            ("历史记录", "history", 1),
            ("设置", "settings", 2),
            ("运行日志", "logs", 3),
        ]
        self.nav_buttons: list[QPushButton] = []
        for label, icon_name, index in nav_items:
            button = QPushButton(f"  {label}")
            button.setObjectName("NavButton")
            button.setIcon(icon(icon_name, theme.MUTED, 18))
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page=index: self.show_page(page))
            self.nav_group.addButton(button, index)
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)
        sidebar_layout.addStretch(1)

        status_frame = QFrame()
        status_frame.setProperty("panel", True)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(5)
        status_row = QHBoxLayout()
        self.sidebar_dot = StatusDot()
        self.sidebar_status = QLabel("准备就绪")
        self.sidebar_status.setStyleSheet("font-size:11px;font-weight:600;")
        status_row.addWidget(self.sidebar_dot)
        status_row.addWidget(self.sidebar_status)
        status_row.addStretch(1)
        status_layout.addLayout(status_row)
        self.session_time = QLabel("本次会话 00:00")
        self.session_time.setProperty("muted", True)
        self.session_time.setStyleSheet("font-size:10px;")
        status_layout.addWidget(self.session_time)
        sidebar_layout.addWidget(status_frame)
        self.quit_button = QPushButton("  退出程序")
        self.quit_button.setIcon(icon("x", theme.MUTED, 16))
        self.quit_button.setProperty("variant", "ghost")
        self.quit_button.clicked.connect(self.quit_requested)
        sidebar_layout.addWidget(self.quit_button)
        root.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.live_page = LivePage(self._settings)
        self.history_page = HistoryPage(self._history)
        self.settings_page = SettingsPage(self._settings, self._secrets)
        self.logs_page = LogsPage()
        self.stack.addWidget(self.live_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.logs_page)
        content_layout.addWidget(self.stack)
        root.addWidget(content, 1)

        self.live_page.start_requested.connect(self.start_requested)
        self.live_page.stop_requested.connect(self.stop_requested)
        self.live_page.manual_requested.connect(self.manual_requested)
        self.live_page.cancel_requested.connect(self.cancel_requested)
        self.live_page.clear_requested.connect(self.clear_requested)
        self.live_page.overlay_requested.connect(self.overlay_requested)
        self.settings_page.save_requested.connect(self.settings_saved)
        self.live_page.set_provider_text(
            self._settings.stt_provider.upper(),
            self._settings.llm_model,
        )

    def replace_history_store(self, history: HistoryStore):
        old_page = self.history_page
        self.history_page = HistoryPage(self._history)
        index = self.stack.indexOf(old_page)
        self.stack.removeWidget(old_page)
        old_page.deleteLater()
        self.stack.insertWidget(index, self.history_page)

    def bind_events(self, events):
        events.state_changed.connect(self._on_state_changed)
        events.transcript_partial.connect(self.live_page.update_partial)
        events.question_final.connect(self.live_page.set_question)
        events.answer_started.connect(lambda _question: self.live_page.begin_answer())
        events.answer_delta.connect(self.live_page.append_answer)
        events.answer_completed.connect(self.live_page.complete_answer)
        events.audio_level.connect(self.live_page.set_audio_level)
        events.session_active_changed.connect(self._set_session_active)
        events.exchange_saved.connect(self.history_page.refresh)

    def bind_log_bridge(self, bridge):
        for record in getattr(bridge, "records", []):
            self.logs_page.append_record(record)
        bridge.record_emitted.connect(self.logs_page.append_record)

    def _on_state_changed(self, state: str, label: str):
        colors = {
            "listening": theme.INFO,
            "recognizing": theme.WARNING,
            "generating": theme.WARNING,
            "ready": theme.ACCENT,
            "error": theme.DANGER,
            "idle": "#9AA4AA",
        }
        self.sidebar_dot.set_color(colors.get(state, "#9AA4AA"))
        self.sidebar_status.setText(label)
        self.live_page.set_state(state, label)

    def _set_session_active(self, active: bool):
        self.live_page.set_active(active)
        self._session_active = active
        self._seconds = 0
        self.session_time.setText("本次会话 00:00")

    def _build_timer(self):
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self._clock.start()
        self._seconds = 0

    def _tick(self):
        if not self._session_active:
            return
        self._seconds += 1
        minutes, seconds = divmod(self._seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            self.session_time.setText(f"本次会话 {hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.session_time.setText(f"本次会话 {minutes:02d}:{seconds:02d}")

    def show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
            color = theme.ACCENT if i == index else theme.MUTED
            icon_name = ("activity", "history", "settings", "logs")[i]
            button.setIcon(icon(icon_name, color, 18))
        if index == 1:
            self.history_page.refresh()

    def settings_saved_feedback(self, failed_secrets: list[str]):
        if failed_secrets:
            self.settings_page.save_button.setText("  密钥保存失败")
        else:
            self.settings_page.save_button.setText("  已保存")
        QTimer.singleShot(
            1600,
            lambda: self.settings_page.save_button.setText("  保存设置"),
        )

    def apply_settings(self, settings: AppSettings, secrets: Secrets):
        self._settings = settings
        self._secrets = secrets
        self.live_page.apply_settings(settings)
        self.settings_page.load_values(settings, secrets)

    def closeEvent(self, event: QCloseEvent):
        if self._force_close:
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.hide_to_tray.emit()

    def force_close(self):
        self._force_close = True
        self.close()

    def notify_error(self, title: str, message: str):
        self.live_page.question_state.setText(title)
        self.logs_page.append_record(
            {
                "timestamp": "",
                "level": "ERROR",
                "source": "ui",
                "message": message,
            }
        )
