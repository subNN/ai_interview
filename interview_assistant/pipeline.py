from __future__ import annotations

import threading
import time
from pathlib import Path
from queue import Empty

from PySide6.QtCore import QThread, Signal

from .core.audio import AudioCapture
from .core.llm import LlmClient, LlmError
from .core.stt import SttEngine, SttError
from .core.text import (
    build_system_prompt,
    correct_keywords,
    load_keyword_map,
    load_qa_bank,
    match_qa_bank,
    match_quick_response,
)
from .config import resource_path
from .history import HistoryStore
from .logging_utils import get_logger
from .models import AppSettings, Secrets


class PipelineThread(QThread):
    state_changed = Signal(str, str)
    transcript_partial = Signal(str)
    question_final = Signal(str)
    answer_started = Signal(str)
    answer_delta = Signal(str)
    answer_completed = Signal(str, int)
    audio_level = Signal(float)
    exchange_saved = Signal()
    error = Signal(str, str)

    def __init__(
        self,
        settings: AppSettings,
        secrets: Secrets,
        resume_text: str,
        session_id: str,
        history: HistoryStore,
    ):
        super().__init__()
        self.settings = settings
        self.secrets = secrets
        self.resume_text = resume_text
        self.session_id = session_id
        self.history_store = history
        self._stop_event = threading.Event()
        self._cancel_answer = threading.Event()
        self._manual_event = threading.Event()
        self._logger = get_logger("pipeline")
        self._keywords = load_keyword_map(resource_path("keywords.txt"))
        self._qa_bank = load_qa_bank(resource_path("qa_bank.json"))
        self._conversation: list[dict[str, str]] = []
        self._audio: AudioCapture | None = None

    def request_stop(self):
        self._stop_event.set()
        self._cancel_answer.set()

    def request_manual(self):
        self._manual_event.set()

    def cancel_answer(self):
        self._cancel_answer.set()

    def clear_conversation(self):
        self._conversation.clear()

    def run(self):
        self._audio = AudioCapture(
            self.settings,
            on_level=self.audio_level.emit,
            on_status=lambda message: self._logger.info(message),
        )
        try:
            self._audio.start()
            self.state_changed.emit("listening", "正在监听")
            self._logger.info("会话已开始，正在监听音频")
            self._run_batch_loop()
        except Exception as exc:
            detail = str(exc)
            self._logger.exception("音频会话异常结束")
            self.error.emit("音频或识别服务启动失败", detail)
            self.state_changed.emit("error", "需要处理")
        finally:
            if self._audio:
                self._audio.stop()
            self.state_changed.emit("idle", "已停止")
            self._logger.info("会话已停止")

    def _run_streaming_loop(self):
        assert self._audio is not None
        stt = SttEngine(self.settings, self.secrets)
        final_silence = 1.5
        while not self._stop_event.is_set():
            if self._consume_manual_trigger(stt):
                continue
            self.state_changed.emit("listening", "正在监听")
            first = ""
            while not self._stop_event.is_set():
                if self._consume_manual_trigger(stt):
                    break
                try:
                    item = self._audio.stream_queue.get(timeout=0.1)
                except Empty:
                    continue
                if item is not AudioCapture.STREAM_START:
                    continue
                self.state_changed.emit("recognizing", "正在识别问题")
                self.transcript_partial.emit("")
                try:
                    first = stt.transcribe_streaming(
                        self._audio.stream_queue,
                        started=True,
                        on_partial=self.transcript_partial.emit,
                        stop_event=self._stop_event,
                    )
                except SttError as exc:
                    self._emit_error("语音识别失败", str(exc))
                    continue
                first = correct_keywords(first, self._keywords)
                if len(first.strip()) >= 2:
                    break
            if not first or self._stop_event.is_set():
                continue

            parts = [first]
            silence_started = time.monotonic()
            while (
                not self._stop_event.is_set()
                and time.monotonic() - silence_started < final_silence
            ):
                try:
                    item = self._audio.stream_queue.get(timeout=0.1)
                except Empty:
                    continue
                if item is not AudioCapture.STREAM_START:
                    continue
                self.state_changed.emit("recognizing", "正在补充识别")
                try:
                    more = stt.transcribe_streaming(
                        self._audio.stream_queue,
                        started=True,
                        on_partial=self.transcript_partial.emit,
                        stop_event=self._stop_event,
                    )
                except SttError as exc:
                    self._emit_error("补充识别失败", str(exc))
                    continue
                more = correct_keywords(more, self._keywords)
                if len(more.strip()) >= 2:
                    parts.append(more)
                    silence_started = time.monotonic()
            self._handle_question("".join(parts))

    def _run_batch_loop(self):
        assert self._audio is not None
        stt = SttEngine(self.settings, self.secrets)
        while not self._stop_event.is_set():
            if self._consume_manual_trigger(stt):
                continue
            try:
                audio_data = self._audio.segment_queue.get(timeout=0.15)
            except Empty:
                continue
            self._transcribe_batch(stt, audio_data)

    def _consume_manual_trigger(self, stt: SttEngine) -> bool:
        if not self._manual_event.is_set():
            return False
        self._manual_event.clear()
        if self._audio is None:
            return False
        audio_data = self._audio.get_recent(5.0)
        if len(audio_data) < 16000:
            self._emit_error("音频数据不足", "最近 5 秒没有足够的音频数据")
            return True
        self._transcribe_batch(stt, audio_data)
        return True

    def _transcribe_batch(self, stt: SttEngine, audio_data: bytes):
        self.state_changed.emit("recognizing", "\u6b63\u5728\u8bc6\u522b\u95ee\u9898")
        self.transcript_partial.emit("")
        try:
            question = stt.transcribe(audio_data)
        except SttError as exc:
            self._emit_error("\u8bed\u97f3\u8bc6\u522b\u5931\u8d25", str(exc))
            return
        self._logger.info("\u8bed\u97f3\u8bc6\u522b\u539f\u59cb\u7ed3\u679c\uff1a%s", question)
        question = correct_keywords(question, self._keywords)
        if len(question.strip()) >= 2:
            self._handle_question(question)
        else:
            self._logger.warning("\u8bed\u97f3\u8bc6\u522b\u672a\u8fd4\u56de\u6709\u6548\u6587\u672c")
            self.state_changed.emit("listening", "\u6b63\u5728\u76d1\u542c")

    def _handle_question(self, question: str):
        if not question.strip():
            return
        self.question_final.emit(question)
        self._logger.info("面试官问题：%s", question)
        quick = match_quick_response(question, self.settings.self_intro)
        quick = quick or match_qa_bank(question, self._qa_bank)
        if quick:
            self.answer_started.emit(question)
            self.answer_delta.emit(quick)
            self._finish_answer(question, quick, 0)
            return

        self.state_changed.emit("generating", "正在生成回答")
        self.answer_started.emit(question)
        self._cancel_answer.clear()
        system_prompt = build_system_prompt(self.settings, self.resume_text)
        started = time.monotonic()
        try:
            llm = LlmClient(self.settings, self.secrets, system_prompt)
            answer = llm.ask_stream(
                question,
                self._conversation,
                self.answer_delta.emit,
                self._cancel_answer,
            )
        except LlmError as exc:
            self._emit_error("回答生成失败", str(exc))
            return
        latency_ms = int((time.monotonic() - started) * 1000)
        self._finish_answer(question, answer, latency_ms)

    def _finish_answer(self, question: str, answer: str, latency_ms: int):
        if not answer.startswith("[已停止"):
            self._conversation.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
            )
        self._logger.info("回答建议：%s", answer)
        if self.settings.history_enabled and answer.strip():
            try:
                self.history_store.add_exchange(
                    self.session_id,
                    question,
                    answer,
                    latency_ms,
                )
            except Exception:
                self._logger.exception("保存历史记录失败")
        self.exchange_saved.emit()
        self.answer_completed.emit(answer, latency_ms)
        self.state_changed.emit("ready", "回答已生成")
        if not self._stop_event.is_set():
            self.state_changed.emit("listening", "正在监听")

    def _emit_error(self, user_message: str, detail: str):
        self._logger.error("%s：%s", user_message, detail)
        self.error.emit(user_message, detail)
        self.state_changed.emit("error", "需要处理")
