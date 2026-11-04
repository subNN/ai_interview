from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .config import ConfigManager, application_dir
from .core.text import discover_resume, read_resume
from .core.tts import SpeechService
from .events import ApplicationEvents
from .history import HistoryStore
from .models import AppSettings, Secrets, SessionState
from .pipeline import PipelineThread


class ApplicationController(QObject):
    settings_applied = Signal(object, object)
    settings_save_completed = Signal(object)

    def __init__(
        self,
        config: ConfigManager,
        history: HistoryStore,
        settings: AppSettings,
        secrets: Secrets,
        logger,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.history = history
        self.settings = settings
        self.secrets = secrets
        self.logger = logger
        self.events = ApplicationEvents(self)
        self.tts = SpeechService()
        self._pipeline: PipelineThread | None = None
        self._session_id: str | None = None
        self._resume_text = ""
        self._restart_pending = False
        self._shutting_down = False
        self._load_resume()

    @property
    def is_active(self) -> bool:
        return self._pipeline is not None and self._pipeline.isRunning()

    @property
    def resume_text(self) -> str:
        return self._resume_text

    def _load_resume(self):
        path = Path(self.settings.resume_path) if self.settings.resume_path else discover_resume(application_dir())
        if path and path.exists():
            self._resume_text = read_resume(path)
            if self._resume_text:
                self.logger.info("已读取简历：%s", path.name)
                return
        self._resume_text = ""
        self.logger.info("未找到可用简历，将使用通用面试提示词")

    def _validate(self) -> bool:
        llm_key = (
            self.secrets.deepseek_api_key
            if self.settings.llm_provider == "deepseek"
            else self.secrets.openai_api_key
        ).strip()
        if not llm_key:
            self.events.error.emit("未配置 AI API Key", "请先在设置中填写当前模型供应商的 API Key。")
            return False
        if self.settings.stt_provider == "xunfei" and not all(
            (
                self.secrets.iflytek_app_id,
                self.secrets.iflytek_api_key,
                self.secrets.iflytek_api_secret,
            )
        ):
            self.events.error.emit("讯飞凭证不完整", "请在设置中补齐讯飞 App ID、API Key 和 Secret。")
            return False
        return True

    def start_session(self):
        if self._shutting_down or self.is_active:
            return
        if not self._validate():
            self.events.state_changed.emit(SessionState.ERROR.value, "需要处理")
            return
        self._load_resume()
        if self.settings.history_enabled:
            self._session_id = self.history.start_session(
                self.settings.audio_source,
                self.settings.llm_model,
            )
        else:
            self._session_id = None
        pipeline = PipelineThread(
            self.settings,
            self.secrets,
            self._resume_text,
            self._session_id or "",
            self.history,
        )
        self._pipeline = pipeline
        pipeline.state_changed.connect(self.events.state_changed)
        pipeline.transcript_partial.connect(self.events.transcript_partial)
        pipeline.question_final.connect(self.events.question_final)
        pipeline.answer_started.connect(self.events.answer_started)
        pipeline.answer_delta.connect(self.events.answer_delta)
        pipeline.answer_completed.connect(self._on_answer_completed)
        pipeline.audio_level.connect(self.events.audio_level)
        pipeline.error.connect(self._on_error)
        pipeline.exchange_saved.connect(self.events.exchange_saved)
        pipeline.finished.connect(self._on_pipeline_finished)
        self.events.session_active_changed.emit(True)
        self.events.state_changed.emit(SessionState.LISTENING.value, "正在启动")
        self.logger.info("正在启动面试会话")
        pipeline.start()

    def stop_session(self, restart: bool = False):
        self._restart_pending = restart
        if self._pipeline is None:
            self.events.session_active_changed.emit(False)
            self.events.state_changed.emit(SessionState.IDLE.value, "已停止")
            return
        self.events.state_changed.emit(SessionState.IDLE.value, "正在停止")
        self._pipeline.request_stop()

    def toggle_session(self):
        self.stop_session() if self.is_active else self.start_session()

    def manual_trigger(self):
        if self._pipeline is not None:
            self._pipeline.request_manual()

    def cancel_answer(self):
        if self._pipeline is not None:
            self._pipeline.cancel_answer()

    def clear_conversation(self):
        if self._pipeline is not None:
            self._pipeline.clear_conversation()
        self.events.conversation_cleared.emit()
        self.logger.info("已清空当前对话")

    def _on_answer_completed(self, answer: str, latency_ms: int):
        self.events.answer_completed.emit(answer, latency_ms)
        if self.settings.enable_tts:
            self.tts.speak_async(answer)

    def _on_error(self, user_message: str, detail: str):
        self.events.error.emit(user_message, detail)

    def _on_pipeline_finished(self):
        pipeline = self._pipeline
        self._pipeline = None
        if pipeline is not None:
            pipeline.deleteLater()
        if self._session_id:
            try:
                self.history.end_session(self._session_id)
            except Exception:
                self.logger.exception("结束会话记录失败")
        self._session_id = None
        self.events.session_active_changed.emit(False)
        self.events.state_changed.emit(SessionState.IDLE.value, "已停止")
        if self._restart_pending and not self._shutting_down:
            self._restart_pending = False
            QTimer.singleShot(150, self.start_session)
        else:
            self._restart_pending = False

    def save_settings(self, settings: AppSettings, secrets: Secrets):
        was_active = self.is_active
        self.settings = settings.normalized()
        self.secrets = secrets
        failed = self.config.save(self.settings, self.secrets)
        self.settings_save_completed.emit(failed)
        if failed:
            self.logger.error("以下密钥未能保存到 Windows 凭据管理器：%s", ", ".join(failed))
        else:
            self.logger.info("设置已保存")
        self._load_resume()
        self.settings_applied.emit(self.settings, self.secrets)
        if was_active:
            self.stop_session(restart=True)

    def persist_overlay_geometry(self, x: int, y: int, width: int, height: int):
        self.settings.overlay_x = x
        self.settings.overlay_y = y
        self.settings.overlay_width = width
        self.settings.overlay_height = height
        self.config.save_settings(self.settings)
        self.settings_applied.emit(self.settings, self.secrets)

    def persist_overlay_opacity(self, opacity: float):
        self.settings.overlay_opacity = opacity
        self.config.save_settings(self.settings)
        self.settings_applied.emit(self.settings, self.secrets)

    def persist_overlay_font_size(self, size: int):
        self.settings.overlay_font_size = size
        self.config.save_settings(self.settings)
        self.settings_applied.emit(self.settings, self.secrets)

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self._restart_pending = False
        self.tts.stop()
        pipeline = self._pipeline
        if pipeline is not None:
            pipeline.request_stop()
            if not pipeline.wait(5000):
                self.logger.error("工作线程未在超时内退出，正在强制结束")
                pipeline.terminate()
                pipeline.wait(1000)
            self._pipeline = None
        if self._session_id:
            try:
                self.history.end_session(self._session_id)
            except Exception:
                pass
            self._session_id = None
