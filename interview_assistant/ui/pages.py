from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import ssl
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.audio import list_input_devices
from ..history import HistoryStore
from ..models import AppSettings, Exchange, Secrets
from . import theme
from .icons import icon
from .widgets import DoubleSpinBox, IconButton, LogView, Metric, PageHeading, SecretLineEdit, SpinBox


class LivePage(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    manual_requested = Signal()
    cancel_requested = Signal()
    clear_requested = Signal()
    overlay_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._active = False
        self._last_answer = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.addWidget(
            PageHeading(
                "实时面试",
                "控制中心可留在后台，面试过程中主要通过悬浮阅读窗查看回答。",
            ),
            1,
        )
        self.start_button = QPushButton("  开始监听")
        self.start_button.setProperty("variant", "primary")
        self.start_button.setIcon(icon("play", "#FFFFFF", 16))
        self.start_button.clicked.connect(self._toggle_session)
        top.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.audio_metric = Metric("音频电平", "等待输入")
        self.stt_metric = Metric("语音识别", self._settings.stt_provider.upper())
        self.llm_metric = Metric("AI 模型", self._settings.llm_model)
        self.latency_metric = Metric("最近响应", "—")
        for metric in (self.audio_metric, self.stt_metric, self.llm_metric, self.latency_metric):
            metrics.addWidget(metric, 1)
        layout.addLayout(metrics)

        live_panel = QFrame()
        live_panel.setProperty("panel", True)
        live_layout = QVBoxLayout(live_panel)
        live_layout.setContentsMargins(16, 14, 16, 14)
        live_layout.setSpacing(12)

        question_header = QHBoxLayout()
        question_title = QLabel("当前问题")
        question_title.setObjectName("SectionTitle")
        question_header.addWidget(question_title)
        question_header.addStretch(1)
        self.question_state = QLabel("等待面试官提问")
        self.question_state.setProperty("muted", True)
        question_header.addWidget(self.question_state)
        live_layout.addLayout(question_header)
        self.question_view = QTextBrowser()
        self.question_view.setPlaceholderText("等待面试官提问...")
        self.question_view.setMinimumHeight(88)
        self.question_view.setMaximumHeight(150)
        live_layout.addWidget(self.question_view)

        answer_header = QHBoxLayout()
        answer_title = QLabel("回答建议")
        answer_title.setObjectName("SectionTitle")
        answer_header.addWidget(answer_title)
        answer_header.addStretch(1)
        self.copy_button = QPushButton("  复制回答")
        self.copy_button.setIcon(icon("copy", theme.TEXT, 15))
        self.copy_button.setProperty("variant", "ghost")
        self.copy_button.clicked.connect(self._copy_answer)
        self.copy_button.setEnabled(False)
        answer_header.addWidget(self.copy_button)
        live_layout.addLayout(answer_header)
        self.answer_view = QTextBrowser()
        self.answer_view.setPlaceholderText("识别到问题后，回答会在这里实时生成。")
        live_layout.addWidget(self.answer_view, 1)
        layout.addWidget(live_panel, 1)

        actions = QHBoxLayout()
        self.manual_button = QPushButton("  手动识别最近 5 秒")
        self.manual_button.setIcon(icon("refresh", theme.TEXT, 15))
        self.manual_button.clicked.connect(self.manual_requested)
        self.manual_button.setEnabled(False)
        self.clear_button = QPushButton("  清空对话")
        self.clear_button.setIcon(icon("trash", theme.TEXT, 15))
        self.clear_button.clicked.connect(self.clear_requested)
        self.cancel_button = QPushButton("  停止生成")
        self.cancel_button.setIcon(icon("square", theme.DANGER, 15))
        self.cancel_button.setProperty("variant", "danger")
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.cancel_button.hide()
        self.overlay_button = QPushButton("  显示悬浮窗")
        self.overlay_button.setIcon(icon("layout", theme.TEXT, 15))
        self.overlay_button.clicked.connect(self.overlay_requested)
        actions.addWidget(self.manual_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.overlay_button)
        layout.addLayout(actions)

    def apply_settings(self, settings: AppSettings):
        self._settings = settings
        self.stt_metric.set_value(settings.stt_provider.upper())
        self.llm_metric.set_value(settings.llm_model)

    def set_provider_text(self, stt: str, llm: str):
        self.stt_metric.set_value(stt)
        self.llm_metric.set_value(llm)

    def _toggle_session(self):
        if self._active:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

    def set_active(self, active: bool):
        self._active = active
        self.manual_button.setEnabled(active)
        if active:
            self.start_button.setText("  停止监听")
            self.start_button.setIcon(icon("square", "#FFFFFF", 15))
        else:
            self.start_button.setText("  开始监听")
            self.start_button.setIcon(icon("play", "#FFFFFF", 16))

    def set_state(self, state: str, label: str):
        self.question_state.setText(label)
        self.cancel_button.setVisible(state == "generating")
        if state == "listening":
            self.audio_metric.set_value("正常")
        elif state in {"recognizing", "generating"}:
            self.audio_metric.set_value("采集中")
        elif state == "error":
            self.audio_metric.set_value("需要处理")

    def set_audio_level(self, value: float):
        if value < 5:
            self.audio_metric.set_value("静音")
        elif value < 30:
            self.audio_metric.set_value("正常")
        else:
            self.audio_metric.set_value("较强")

    def update_partial(self, text_value: str):
        if not text_value:
            self.question_view.clear()
        else:
            self.question_view.setPlainText(text_value)
            self.question_view.moveCursor(QTextCursor.MoveOperation.End)

    def set_question(self, question: str):
        self.question_view.setPlainText(question)
        self.question_state.setText("问题已确认")

    def begin_answer(self):
        self.answer_view.clear()
        self._last_answer = ""
        self.copy_button.setEnabled(False)

    def append_answer(self, text_value: str):
        scrollbar = self.answer_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 3
        self.answer_view.moveCursor(QTextCursor.MoveOperation.End)
        self.answer_view.insertPlainText(text_value)
        self._last_answer += text_value
        if at_bottom:
            self.answer_view.moveCursor(QTextCursor.MoveOperation.End)
            self.answer_view.ensureCursorVisible()

    def complete_answer(self, answer: str, latency_ms: int):
        self._last_answer = answer
        self.answer_view.setPlainText(answer)
        self.copy_button.setEnabled(bool(answer))
        self.latency_metric.set_value(f"{latency_ms / 1000:.1f} s" if latency_ms else "即时")
        self.answer_view.moveCursor(QTextCursor.MoveOperation.End)

    def clear_content(self):
        self.question_view.clear()
        self.answer_view.clear()
        self._last_answer = ""
        self.copy_button.setEnabled(False)
        self.question_state.setText("等待面试官提问")
        self.latency_metric.set_value("—")
        self.cancel_button.hide()

    def _copy_answer(self):
        if self._last_answer:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._last_answer)
            self.copy_button.setText("  已复制")
            QTimer.singleShot(1200, lambda: self.copy_button.setText("  复制回答"))


class HistoryPage(QWidget):
    def __init__(self, store: HistoryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._exchanges: list[Exchange] = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self.refresh)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(PageHeading("历史记录", "回看本地保存的问题与回答。"), 1)
        self.clear_button = QPushButton("  清空历史")
        self.clear_button.setIcon(icon("trash", theme.DANGER, 15))
        self.clear_button.setProperty("variant", "danger")
        self.clear_button.clicked.connect(self._clear)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索问题或回答")
        self.search_edit.addAction(icon("search", theme.MUTED, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())
        self.count_label = QLabel("0 条记录")
        self.count_label.setProperty("muted", True)
        toolbar.addWidget(self.search_edit, 1)
        toolbar.addWidget(self.count_label)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(270)
        self.list_widget.currentRowChanged.connect(self._show_row)
        splitter.addWidget(self.list_widget)
        self.detail = QTextBrowser()
        self.detail.setPlaceholderText("选择一条历史记录查看详情。")
        splitter.addWidget(self.detail)
        splitter.setSizes([320, 650])
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("  复制回答")
        self.copy_button.setIcon(icon("copy", theme.TEXT, 15))
        self.copy_button.clicked.connect(self._copy)
        self.copy_button.setEnabled(False)
        actions.addStretch(1)
        actions.addWidget(self.copy_button)
        layout.addLayout(actions)

    def refresh(self):
        self._exchanges = self.store.list_exchanges(self.search_edit.text() if hasattr(self, "search_edit") else "")
        self.list_widget.clear()
        for exchange in self._exchanges:
            timestamp = exchange.created_at.replace("T", " ")[:16]
            preview = exchange.question.replace("\n", " ")[:34]
            item = QListWidgetItem(f"{timestamp}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, exchange.id)
            self.list_widget.addItem(item)
        self.count_label.setText(f"{len(self._exchanges)} 条记录")
        if self._exchanges:
            self.list_widget.setCurrentRow(0)
        else:
            self.detail.clear()
            self.copy_button.setEnabled(False)

    def _show_row(self, index: int):
        if index < 0 or index >= len(self._exchanges):
            self.copy_button.setEnabled(False)
            return
        exchange = self._exchanges[index]
        created = exchange.created_at.replace("T", " ")
        latency = f"{exchange.latency_ms / 1000:.1f} 秒" if exchange.latency_ms else "即时"
        self.detail.setHtml(
            f"<p style='color:{theme.MUTED};font-size:12px'>{created} · 响应 {latency}</p>"
            f"<h3 style='color:#A8660B;font-size:15px'>面试官提问</h3>"
            f"<p style='font-size:15px;line-height:1.7'>{self._html(exchange.question)}</p>"
            f"<h3 style='color:{theme.ACCENT};font-size:15px'>回答建议</h3>"
            f"<p style='font-size:15px;line-height:1.7'>{self._html(exchange.answer)}</p>"
        )
        self.copy_button.setEnabled(True)

    @staticmethod
    def _html(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    def _copy(self):
        index = self.list_widget.currentRow()
        if 0 <= index < len(self._exchanges):
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._exchanges[index].answer)

    def _clear(self):
        answer = QMessageBox.question(
            self,
            "清空历史",
            "确定删除全部本地问答记录吗？此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.clear()
            self.refresh()


def _model_api_urls(api_base: str) -> list[str]:
    base = api_base.strip().rstrip("/")
    if not base:
        raise ValueError("API \u5730\u5740\u4e0d\u80fd\u4e3a\u7a7a\u3002")
    if not base.startswith(("http://", "https://")):
        raise ValueError("API \u5730\u5740\u5fc5\u987b\u4ee5 http:// \u6216 https:// \u5f00\u5934\u3002")
    if base.endswith("/models"):
        return [base]
    if base.endswith("/v1"):
        return [base + "/models"]
    return [base + "/models", base + "/v1/models"]


def _extract_model_ids(payload) -> list[str]:
    if isinstance(payload, dict):
        for key in ("data", "models", "items"):
            if key in payload:
                payload = payload[key]
                break
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    found = []
    seen = set()
    for item in payload:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            model_id = str(
                item.get("id")
                or item.get("name")
                or item.get("model")
                or ""
            ).strip()
        else:
            model_id = ""
        if model_id and model_id not in seen:
            seen.add(model_id)
            found.append(model_id)
    return found


def _fetch_model_ids(api_base: str, api_key: str) -> list[str]:
    urls = _model_api_urls(api_base)
    headers = {"Accept": "application/json", "User-Agent": "AI-Interview-Assistant/1.1"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    errors = []
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        kwargs = {"timeout": 12}
        if url.startswith("https://") and host in {"127.0.0.1", "localhost", "::1"}:
            kwargs["context"] = ssl._create_unverified_context()
        request = urlrequest.Request(url, headers=headers, method="GET")
        try:
            with urlrequest.urlopen(request, **kwargs) as response:
                body = response.read().decode("utf-8", errors="replace")
            models = _extract_model_ids(json.loads(body))
            if models:
                return models
            errors.append(f"{url}: \u672a\u8fd4\u56de\u6a21\u578b\u5217\u8868")
        except urlerror.HTTPError as exc:
            errors.append(f"{url}: HTTP {exc.code}")
            if exc.code in (401, 403):
                break
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("\n".join(errors) or "\u672a\u83b7\u53d6\u5230\u6a21\u578b\u5217\u8868\u3002")


def _chat_completion_urls(api_base: str) -> list[str]:
    base = api_base.strip().rstrip("/")
    if not base:
        raise ValueError("API \u5730\u5740\u4e0d\u80fd\u4e3a\u7a7a\u3002")
    if not base.startswith(("http://", "https://")):
        raise ValueError("API \u5730\u5740\u5fc5\u987b\u4ee5 http:// \u6216 https:// \u5f00\u5934\u3002")
    if base.endswith("/chat/completions"):
        return [base]
    if base.endswith("/v1"):
        return [base + "/chat/completions"]
    return [base + "/chat/completions", base + "/v1/chat/completions"]


def _extract_ai_reply(payload) -> str:
    if not isinstance(payload, dict):
        raise ValueError("AI \u8fd4\u56de\u683c\u5f0f\u4e0d\u6b63\u786e\u3002")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("AI \u54cd\u5e94\u4e2d\u6ca1\u6709 choices\u3002")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    if content is None:
        content = choice.get("text") or payload.get("response") or payload.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", "")) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "").strip()


def _test_ai_endpoint(api_base: str, api_key: str, model: str) -> str:
    model = model.strip()
    if not model:
        raise ValueError("\u8bf7\u5148\u586b\u5199\u6a21\u578b\u540d\u79f0\u3002")
    urls = _chat_completion_urls(api_base)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "AI-Interview-Assistant/1.1",
    }
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Reply with OK only."}
        ],
        "temperature": 0,
        "max_tokens": 16,
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    errors = []
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        kwargs = {"timeout": 20}
        if url.startswith("https://") and host in {"127.0.0.1", "localhost", "::1"}:
            kwargs["context"] = ssl._create_unverified_context()
        request = urlrequest.Request(url, data=data, headers=headers, method="POST")
        try:
            with urlrequest.urlopen(request, **kwargs) as response:
                body = response.read().decode("utf-8", errors="replace")
            reply = _extract_ai_reply(json.loads(body))
            return reply or "OK"
        except urlerror.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:240]
            except Exception:
                detail = ""
            errors.append(f"{url}: HTTP {exc.code}{' - ' + detail if detail else ''}")
            if exc.code in (401, 403):
                break
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors) or "AI \u6d4b\u8bd5\u5931\u8d25\u3002")


class AITestWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, api_base: str, api_key: str, model: str, parent=None):
        super().__init__(parent)
        self._api_base = api_base
        self._api_key = api_key
        self._model = model

    def run(self):
        try:
            self.completed.emit(_test_ai_endpoint(self._api_base, self._api_key, self._model))
        except Exception as exc:
            self.failed.emit(str(exc))


class ModelListFetcher(QThread):
    completed = Signal(list)
    failed = Signal(str)

    def __init__(self, api_base: str, api_key: str, parent=None):
        super().__init__(parent)
        self._api_base = api_base
        self._api_key = api_key

    def run(self):
        try:
            self.completed.emit(_fetch_model_ids(self._api_base, self._api_key))
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsPage(QWidget):
    save_requested = Signal(object, object)

    def __init__(self, settings: AppSettings, secrets: Secrets, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._secrets = secrets
        self._model_fetch_worker = None
        self._ai_test_worker = None
        self._build_ui()
        self.load_values(settings, secrets)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(PageHeading("设置", "配置音频、语音识别、AI 模型和悬浮窗默认样式。"), 1)
        self.save_button = QPushButton("  保存设置")
        self.save_button.setProperty("variant", "primary")
        self.save_button.setIcon(icon("save", "#FFFFFF", 16))
        self.save_button.clicked.connect(self._save)
        header.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_audio_tab(), "音频与识别")
        self.tabs.addTab(self._build_llm_tab(), "AI 模型")
        self.tabs.addTab(self._build_context_tab(), "简历与提示词")
        self.tabs.addTab(self._build_overlay_tab(), "悬浮窗")
        self.tabs.addTab(self._build_privacy_tab(), "隐私与输出")
        layout.addWidget(self.tabs, 1)

    @staticmethod
    def _scrollable(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _form_container() -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(20, 18, 20, 20)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return page, form

    def _build_audio_tab(self):
        page, form = self._form_container()
        self.audio_source = QComboBox()
        self.audio_source.addItem("系统声音（WASAPI Loopback）", "loopback")
        self.audio_source.addItem("麦克风", "mic")
        self.audio_source.currentIndexChanged.connect(self._sync_audio_device)
        form.addRow("音频来源", self.audio_source)

        device_row = QWidget()
        device_layout = QHBoxLayout(device_row)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(6)
        self.audio_device = QComboBox()
        refresh_button = IconButton("refresh", "刷新音频设备")
        refresh_button.clicked.connect(self._refresh_devices)
        device_layout.addWidget(self.audio_device, 1)
        device_layout.addWidget(refresh_button)
        form.addRow("麦克风设备", device_row)

        self.vad_threshold = DoubleSpinBox()
        self.vad_threshold.setRange(0, 2000)
        self.vad_threshold.setDecimals(0)
        self.vad_threshold.setSuffix(" RMS")
        form.addRow("VAD 阈值", self.vad_threshold)
        self.vad_adaptive = QCheckBox("根据环境噪声自动调整阈值")
        form.addRow("自适应", self.vad_adaptive)
        self.silence_seconds = DoubleSpinBox()
        self.silence_seconds.setRange(0.5, 10.0)
        self.silence_seconds.setSingleStep(0.1)
        self.silence_seconds.setSuffix(" 秒")
        form.addRow("说话结束静音", self.silence_seconds)
        self.min_speech_seconds = DoubleSpinBox()
        self.min_speech_seconds.setRange(0.2, 5.0)
        self.min_speech_seconds.setSingleStep(0.1)
        self.min_speech_seconds.setSuffix(" 秒")
        form.addRow("最短语音", self.min_speech_seconds)

        self.stt_provider = QComboBox()
        self.stt_provider.addItem("讯飞实时听写", "xunfei")
        self.stt_provider.addItem("OpenAI Whisper", "openai")
        self.stt_provider.addItem("本地 Whisper", "local")
        form.addRow("语音识别", self.stt_provider)
        self.stt_language = QComboBox()
        self.stt_language.setEditable(True)
        self.stt_language.addItems(["zh", "en"])
        form.addRow("识别语言", self.stt_language)
        self.stt_model = QLineEdit()
        form.addRow("OpenAI 转写模型", self.stt_model)
        self.local_whisper_model = QComboBox()
        self.local_whisper_model.setEditable(True)
        self.local_whisper_model.addItems(["tiny", "base", "small", "medium", "large"])
        form.addRow("本地模型", self.local_whisper_model)
        self.local_whisper_device = QComboBox()
        self.local_whisper_device.addItems(["cpu", "cuda"])
        form.addRow("本地推理设备", self.local_whisper_device)

        self.iflytek_app_id = QLineEdit()
        self.iflytek_api_key = SecretLineEdit()
        self.iflytek_api_secret = SecretLineEdit()
        form.addRow("讯飞 App ID", self.iflytek_app_id)
        form.addRow("讯飞 API Key", self.iflytek_api_key)
        form.addRow("讯飞 API Secret", self.iflytek_api_secret)
        self._refresh_devices()
        return self._scrollable(page)

    def _build_llm_tab(self):
        page, form = self._form_container()
        self.llm_provider = QComboBox()
        self.llm_provider.addItem("DeepSeek", "deepseek")
        self.llm_provider.addItem("OpenAI", "openai")
        self.llm_provider.addItem("OpenAI \u517c\u5bb9\u670d\u52a1", "custom")
        self.llm_provider.currentIndexChanged.connect(lambda _index: self._apply_llm_defaults())
        form.addRow("\u6a21\u578b\u4f9b\u5e94\u5546", self.llm_provider)

        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(6)
        self.llm_model = QLineEdit()
        self.fetch_models_button = QPushButton("  \u83b7\u53d6\u6a21\u578b")
        self.fetch_models_button.setIcon(icon("refresh", theme.TEXT, 15))
        self.fetch_models_button.setToolTip("\u4ece API \u83b7\u53d6\u53ef\u7528\u6a21\u578b\u5217\u8868")
        self.fetch_models_button.clicked.connect(self._fetch_llm_models)
        self.test_ai_button = QPushButton("  \u6d4b\u8bd5 AI")
        self.test_ai_button.setIcon(icon("check", theme.TEXT, 15))
        self.test_ai_button.setToolTip("\u4f7f\u7528\u5f53\u524d API \u5730\u5740\u3001\u6a21\u578b\u548c\u5bc6\u94a5\u6d4b\u8bd5 AI \u662f\u5426\u53ef\u7528")
        self.test_ai_button.clicked.connect(self._test_llm)
        model_layout.addWidget(self.llm_model, 1)
        model_layout.addWidget(self.fetch_models_button)
        model_layout.addWidget(self.test_ai_button)
        form.addRow("\u6a21\u578b\u540d\u79f0", model_row)

        self.llm_api_base = QLineEdit()
        self.llm_api_base.setPlaceholderText("https://api.deepseek.com")
        form.addRow("API \u5730\u5740", self.llm_api_base)
        self.deepseek_api_key = SecretLineEdit()
        form.addRow("DeepSeek Key", self.deepseek_api_key)
        self.openai_api_key = SecretLineEdit()
        form.addRow("OpenAI Key", self.openai_api_key)
        self.llm_thinking_enabled = QCheckBox("\u542f\u7528\u6df1\u5ea6\u601d\u8003\uff08\u54cd\u5e94\u66f4\u6162\uff0c\u9ed8\u8ba4\u5173\u95ed\uff09")
        form.addRow("\u6df1\u5ea6\u601d\u8003", self.llm_thinking_enabled)
        self.llm_temperature = DoubleSpinBox()
        self.llm_temperature.setRange(0, 2)
        self.llm_temperature.setSingleStep(0.1)
        form.addRow("\u56de\u7b54\u6e29\u5ea6", self.llm_temperature)
        self.llm_max_tokens = SpinBox()
        self.llm_max_tokens.setRange(64, 8192)
        self.llm_max_tokens.setSingleStep(64)
        form.addRow("\u6700\u5927\u4ee4\u724c\u6570", self.llm_max_tokens)
        self.max_history = SpinBox()
        self.max_history.setRange(0, 30)
        form.addRow("\u5bf9\u8bdd\u5386\u53f2\u8f6e\u6570", self.max_history)
        return self._scrollable(page)

    def _build_context_tab(self):
        page, form = self._form_container()
        resume_row = QWidget()
        resume_layout = QHBoxLayout(resume_row)
        resume_layout.setContentsMargins(0, 0, 0, 0)
        self.resume_path = QLineEdit()
        browse = IconButton("folder", "选择简历文件")
        browse.clicked.connect(self._browse_resume)
        resume_layout.addWidget(self.resume_path, 1)
        resume_layout.addWidget(browse)
        form.addRow("简历文件", resume_row)
        self.self_intro = QTextEdit()
        self.self_intro.setPlaceholderText("面试官要求自我介绍时直接返回的内容。留空则交给 AI。")
        self.self_intro.setMinimumHeight(100)
        form.addRow("自我介绍模板", self.self_intro)
        self.system_prompt = QTextEdit()
        self.system_prompt.setPlaceholderText("留空使用默认面试助手提示词。")
        self.system_prompt.setMinimumHeight(170)
        form.addRow("系统提示词", self.system_prompt)
        return self._scrollable(page)

    def _build_overlay_tab(self):
        page, form = self._form_container()
        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        self.overlay_width = SpinBox()
        self.overlay_width.setRange(560, 1600)
        self.overlay_width.setSuffix(" px")
        self.overlay_height = SpinBox()
        self.overlay_height.setRange(360, 1200)
        self.overlay_height.setSuffix(" px")
        size_layout.addWidget(self.overlay_width)
        size_layout.addWidget(QLabel("×"))
        size_layout.addWidget(self.overlay_height)
        size_layout.addStretch(1)
        form.addRow("默认尺寸", size_row)
        self.overlay_font_size = SpinBox()
        self.overlay_font_size.setRange(16, 32)
        self.overlay_font_size.setSuffix(" px")
        form.addRow("回答字号", self.overlay_font_size)
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity.setRange(65, 100)
        self.opacity_label = QLabel("96%")
        self.opacity_label.setFixedWidth(42)
        self.overlay_opacity.valueChanged.connect(lambda value: self.opacity_label.setText(f"{value}%"))
        opacity_layout.addWidget(self.overlay_opacity, 1)
        opacity_layout.addWidget(self.opacity_label)
        form.addRow("不透明度", opacity_row)
        self.overlay_always_on_top = QCheckBox("始终显示在其他窗口上方")
        form.addRow("窗口层级", self.overlay_always_on_top)
        note = QLabel("悬浮窗本身也可以直接拖动边框缩放，并通过标题栏滑块即时调节透明度。")
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addRow("", note)
        return self._scrollable(page)

    def _build_privacy_tab(self):
        page, form = self._form_container()
        self.history_enabled = QCheckBox("在本地保存问答历史")
        form.addRow("历史记录", self.history_enabled)
        self.log_retention_days = SpinBox()
        self.log_retention_days.setRange(1, 365)
        self.log_retention_days.setSuffix(" 天")
        form.addRow("日志保留", self.log_retention_days)
        self.enable_tts = QCheckBox("生成完成后朗读回答")
        form.addRow("语音播报", self.enable_tts)
        note = QLabel(
            "API Key 通过 Windows 凭据管理器保存。日志会隐藏密钥和授权字段，"
            "安装目录不会写入用户配置或历史数据。"
        )
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addRow("", note)
        return self._scrollable(page)

    def _llm_api_key(self) -> str:
        provider = self.llm_provider.currentData()
        if provider == "deepseek":
            key = self.deepseek_api_key.text()
        elif provider == "openai":
            key = self.openai_api_key.text()
        else:
            key = self.deepseek_api_key.text() or self.openai_api_key.text()
        return key.strip()

    def _fetch_llm_models(self):
        if self._model_fetch_worker is not None and self._model_fetch_worker.isRunning():
            return
        try:
            _model_api_urls(self.llm_api_base.text())
        except ValueError as exc:
            QMessageBox.warning(self, "\u65e0\u6cd5\u83b7\u53d6\u6a21\u578b", str(exc))
            return
        self.fetch_models_button.setEnabled(False)
        self.fetch_models_button.setText("  \u6b63\u5728\u83b7\u53d6...")
        worker = ModelListFetcher(
            self.llm_api_base.text().strip(),
            self._llm_api_key(),
            self,
        )
        self._model_fetch_worker = worker
        worker.completed.connect(self._models_fetched)
        worker.failed.connect(self._models_fetch_failed)
        worker.finished.connect(self._model_fetch_finished)
        worker.start()

    def _models_fetched(self, models: list[str]):
        self.fetch_models_button.setEnabled(True)
        self.fetch_models_button.setText("  \u83b7\u53d6\u6a21\u578b")
        if not models:
            QMessageBox.information(self, "\u672a\u627e\u5230\u6a21\u578b", "API \u672a\u8fd4\u56de\u53ef\u7528\u6a21\u578b\u3002")
            return
        if len(models) == 1:
            self.llm_model.setText(models[0])
            return
        menu = QMenu(self)
        for model_id in models:
            action = menu.addAction(model_id)
            action.triggered.connect(
                lambda _checked=False, value=model_id: self.llm_model.setText(value)
            )
        menu.exec(
            self.fetch_models_button.mapToGlobal(
                QPoint(0, self.fetch_models_button.height())
            )
        )

    def _models_fetch_failed(self, message: str):
        self.fetch_models_button.setEnabled(True)
        self.fetch_models_button.setText("  \u83b7\u53d6\u6a21\u578b")
        QMessageBox.warning(
            self,
            "\u83b7\u53d6\u6a21\u578b\u5931\u8d25",
            message or "\u8bf7\u68c0\u67e5 API \u5730\u5740\u548c\u5bc6\u94a5\u3002",
        )

    def _test_llm(self):
        if self._ai_test_worker is not None and self._ai_test_worker.isRunning():
            return
        if self._model_fetch_worker is not None and self._model_fetch_worker.isRunning():
            return
        model = self.llm_model.text().strip()
        try:
            _chat_completion_urls(self.llm_api_base.text())
            if not model:
                raise ValueError("\u8bf7\u5148\u586b\u5199\u6a21\u578b\u540d\u79f0\u3002")
        except ValueError as exc:
            QMessageBox.warning(self, "\u65e0\u6cd5\u6d4b\u8bd5 AI", str(exc))
            return
        self.test_ai_button.setEnabled(False)
        self.fetch_models_button.setEnabled(False)
        self.test_ai_button.setText("  \u6d4b\u8bd5\u4e2d...")
        worker = AITestWorker(
            self.llm_api_base.text().strip(),
            self._llm_api_key(),
            model,
            self,
        )
        self._ai_test_worker = worker
        worker.completed.connect(self._ai_test_completed)
        worker.failed.connect(self._ai_test_failed)
        worker.finished.connect(self._ai_test_finished)
        worker.start()

    def _ai_test_completed(self, reply: str):
        self.test_ai_button.setEnabled(True)
        self.fetch_models_button.setEnabled(True)
        self.test_ai_button.setText("  \u6d4b\u8bd5 AI")
        QMessageBox.information(
            self,
            "AI \u6d4b\u8bd5\u6210\u529f",
            f"\u5f53\u524d AI \u53ef\u7528\u3002\n\u6a21\u578b\uff1a{self.llm_model.text().strip()}\n\u54cd\u5e94\uff1a{reply[:200]}",
        )

    def _ai_test_failed(self, message: str):
        self.test_ai_button.setEnabled(True)
        self.fetch_models_button.setEnabled(True)
        self.test_ai_button.setText("  \u6d4b\u8bd5 AI")
        QMessageBox.warning(
            self,
            "AI \u6d4b\u8bd5\u5931\u8d25",
            message or "\u8bf7\u68c0\u67e5 API \u5730\u5740\u3001\u6a21\u578b\u540d\u79f0\u548c\u5bc6\u94a5\u3002",
        )

    def _model_fetch_finished(self):
        self._model_fetch_worker = None

    def _ai_test_finished(self):
        self._ai_test_worker = None

    def _apply_llm_defaults(self):
        provider = self.llm_provider.currentData()
        model = self.llm_model.text().strip()
        api_base = self.llm_api_base.text().strip()
        if provider == "deepseek":
            if not api_base or "api.openai.com" in api_base:
                self.llm_api_base.setText("https://api.deepseek.com")
            if not model or model.startswith("gpt-"):
                self.llm_model.setText("deepseek-chat")
        elif provider == "openai":
            if "api.deepseek.com" in api_base:
                self.llm_api_base.clear()
            if not model or model.startswith("deepseek-"):
                self.llm_model.setText("gpt-4o")

    def _refresh_devices(self):
        current = self.audio_device.currentData() if self.audio_device.count() else None
        self.audio_device.clear()
        self.audio_device.addItem("系统默认输入设备", None)
        for device in list_input_devices():
            self.audio_device.addItem(device["name"], device["index"])
        if current is not None:
            index = self.audio_device.findData(current)
            if index >= 0:
                self.audio_device.setCurrentIndex(index)
        self._sync_audio_device()

    def _sync_audio_device(self):
        self.audio_device.setEnabled(self.audio_source.currentData() == "mic")

    def _browse_resume(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择简历",
            str(Path.home()),
            "简历文件 (*.pdf *.txt);;所有文件 (*.*)",
        )
        if path:
            self.resume_path.setText(path)

    def load_values(self, settings: AppSettings, secrets: Secrets):
        self._settings = settings
        self._secrets = secrets
        self.audio_source.setCurrentIndex(max(0, self.audio_source.findData(settings.audio_source)))
        if settings.audio_device is not None:
            index = self.audio_device.findData(settings.audio_device)
            if index >= 0:
                self.audio_device.setCurrentIndex(index)
        self.vad_threshold.setValue(settings.vad_threshold)
        self.vad_adaptive.setChecked(settings.vad_adaptive)
        self.silence_seconds.setValue(settings.silence_seconds)
        self.min_speech_seconds.setValue(settings.min_speech_seconds)
        self.stt_provider.setCurrentIndex(max(0, self.stt_provider.findData(settings.stt_provider)))
        self.stt_language.setCurrentText(settings.stt_language)
        self.stt_model.setText(settings.stt_model)
        self.local_whisper_model.setCurrentText(settings.local_whisper_model)
        self.local_whisper_device.setCurrentText(settings.local_whisper_device)
        self.iflytek_app_id.setText(secrets.iflytek_app_id)
        self.iflytek_api_key.setText(secrets.iflytek_api_key)
        self.iflytek_api_secret.setText(secrets.iflytek_api_secret)

        self.llm_provider.setCurrentIndex(max(0, self.llm_provider.findData(settings.llm_provider)))
        self.llm_model.setText(settings.llm_model)
        self.llm_api_base.setText(settings.llm_api_base)
        self.deepseek_api_key.setText(secrets.deepseek_api_key)
        self.openai_api_key.setText(secrets.openai_api_key)
        self.llm_thinking_enabled.setChecked(settings.llm_thinking_enabled)
        self.llm_temperature.setValue(settings.llm_temperature)
        self.llm_max_tokens.setValue(settings.llm_max_tokens)
        self.max_history.setValue(settings.max_history)

        self.resume_path.setText(settings.resume_path)
        self.self_intro.setPlainText(settings.self_intro)
        self.system_prompt.setPlainText(settings.system_prompt)
        self.overlay_width.setValue(settings.overlay_width)
        self.overlay_height.setValue(settings.overlay_height)
        self.overlay_font_size.setValue(settings.overlay_font_size)
        self.overlay_opacity.setValue(round(settings.overlay_opacity * 100))
        self.opacity_label.setText(f"{round(settings.overlay_opacity * 100)}%")
        self.overlay_always_on_top.setChecked(settings.overlay_always_on_top)
        self.history_enabled.setChecked(settings.history_enabled)
        self.log_retention_days.setValue(settings.log_retention_days)
        self.enable_tts.setChecked(settings.enable_tts)
        self._sync_audio_device()

    def _collect(self) -> tuple[AppSettings, Secrets]:
        settings = AppSettings(
            audio_source=self.audio_source.currentData(),
            audio_device=self.audio_device.currentData(),
            vad_threshold=self.vad_threshold.value(),
            vad_adaptive=self.vad_adaptive.isChecked(),
            silence_seconds=self.silence_seconds.value(),
            min_speech_seconds=self.min_speech_seconds.value(),
            stt_provider=self.stt_provider.currentData(),
            stt_language=self.stt_language.currentText().strip(),
            stt_model=self.stt_model.text().strip(),
            local_whisper_model=self.local_whisper_model.currentText().strip(),
            local_whisper_device=self.local_whisper_device.currentText().strip(),
            llm_provider=self.llm_provider.currentData(),
            llm_model=self.llm_model.text().strip(),
            llm_api_base=self.llm_api_base.text().strip(),
            llm_thinking_enabled=self.llm_thinking_enabled.isChecked(),
            llm_temperature=self.llm_temperature.value(),
            llm_max_tokens=self.llm_max_tokens.value(),
            max_history=self.max_history.value(),
            resume_path=self.resume_path.text().strip(),
            system_prompt=self.system_prompt.toPlainText().strip(),
            self_intro=self.self_intro.toPlainText().strip(),
            enable_tts=self.enable_tts.isChecked(),
            overlay_width=self.overlay_width.value(),
            overlay_height=self.overlay_height.value(),
            overlay_font_size=self.overlay_font_size.value(),
            overlay_opacity=self.overlay_opacity.value() / 100.0,
            overlay_always_on_top=self.overlay_always_on_top.isChecked(),
            overlay_x=self._settings.overlay_x,
            overlay_y=self._settings.overlay_y,
            history_enabled=self.history_enabled.isChecked(),
            log_retention_days=self.log_retention_days.value(),
        ).normalized()
        secrets = Secrets(
            deepseek_api_key=self.deepseek_api_key.text().strip(),
            openai_api_key=self.openai_api_key.text().strip(),
            iflytek_app_id=self.iflytek_app_id.text().strip(),
            iflytek_api_key=self.iflytek_api_key.text().strip(),
            iflytek_api_secret=self.iflytek_api_secret.text().strip(),
        )
        return settings, secrets

    def _save(self):
        settings, secrets = self._collect()
        self._settings = settings
        self._secrets = secrets
        self.save_requested.emit(settings, secrets)


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(PageHeading("运行日志", "运行状态、识别问题和 AI 回答会同步记录在这里。"), 1)
        self.copy_button = QPushButton("  复制日志")
        self.copy_button.setIcon(icon("copy", theme.TEXT, 15))
        self.copy_button.clicked.connect(self._copy)
        self.clear_button = QPushButton("  清空显示")
        self.clear_button.setIcon(icon("trash", theme.TEXT, 15))
        self.clear_button.clicked.connect(self._clear)
        header.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItem("全部级别", "ALL")
        self.level_filter.addItems(["INFO", "WARNING", "ERROR"])
        self.level_filter.currentIndexChanged.connect(lambda _index: self._rerender())
        self.auto_follow = QCheckBox("自动跟随最新日志")
        self.auto_follow.setChecked(True)
        self.auto_follow.toggled.connect(lambda value: self.log_view.set_auto_follow(value))
        toolbar.addWidget(QLabel("筛选"))
        toolbar.addWidget(self.level_filter)
        toolbar.addStretch(1)
        toolbar.addWidget(self.auto_follow)
        layout.addLayout(toolbar)
        self.log_view = LogView()
        layout.addWidget(self.log_view, 1)

    def append_record(self, record: dict):
        self._records.append(record)
        level_filter = self.level_filter.currentData()
        if level_filter == "ALL" or record.get("level") == level_filter:
            self.log_view.append_record(record)

    def _rerender(self):
        self.log_view.clear()
        level_filter = self.level_filter.currentData()
        for record in self._records:
            if level_filter == "ALL" or record.get("level") == level_filter:
                self.log_view.append_record(record)

    def _copy(self):
        from PySide6.QtWidgets import QApplication

        lines = [
            f"{record['timestamp']} {record['level']:7s} {record['source']} {record['message']}"
            for record in self._records
        ]
        QApplication.clipboard().setText("\n".join(lines))

    def _clear(self):
        self._records.clear()
        self.log_view.clear()
