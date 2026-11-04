from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class SessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECOGNIZING = "recognizing"
    GENERATING = "generating"
    READY = "ready"
    ERROR = "error"


@dataclass
class AppSettings:
    audio_source: str = "loopback"
    audio_device: Optional[int] = None
    vad_threshold: float = 100.0
    vad_adaptive: bool = False
    silence_seconds: float = 1.5
    min_speech_seconds: float = 0.8

    stt_provider: str = "xunfei"
    stt_language: str = "zh"
    stt_model: str = "whisper-1"
    local_whisper_model: str = "medium"
    local_whisper_device: str = "cpu"

    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_api_base: str = "https://api.deepseek.com"
    llm_thinking_enabled: bool = False
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1024
    max_history: int = 5

    resume_path: str = ""
    system_prompt: str = ""
    self_intro: str = ""
    enable_tts: bool = False

    overlay_width: int = 760
    overlay_height: int = 560
    overlay_font_size: int = 20
    overlay_opacity: float = 0.96
    overlay_always_on_top: bool = True
    overlay_x: Optional[int] = None
    overlay_y: Optional[int] = None

    history_enabled: bool = True
    log_retention_days: int = 14

    def normalized(self) -> "AppSettings":
        self.audio_source = self.audio_source if self.audio_source in {"loopback", "mic"} else "loopback"
        self.vad_threshold = max(0.0, float(self.vad_threshold))
        self.silence_seconds = max(0.5, min(10.0, float(self.silence_seconds)))
        self.min_speech_seconds = max(0.2, min(5.0, float(self.min_speech_seconds)))
        self.llm_temperature = max(0.0, min(2.0, float(self.llm_temperature)))
        self.llm_max_tokens = max(64, min(8192, int(self.llm_max_tokens)))
        self.max_history = max(0, min(30, int(self.max_history)))
        self.overlay_width = max(560, min(1600, int(self.overlay_width)))
        self.overlay_height = max(360, min(1200, int(self.overlay_height)))
        self.overlay_font_size = max(16, min(32, int(self.overlay_font_size)))
        self.overlay_opacity = max(0.65, min(1.0, float(self.overlay_opacity)))
        self.log_retention_days = max(1, min(365, int(self.log_retention_days)))
        if self.stt_provider not in {"xunfei", "openai", "local"}:
            self.stt_provider = "xunfei"
        return self

    @classmethod
    def from_env(cls) -> "AppSettings":
        def env_bool(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).strip().lower() not in {"0", "false", "no", "off"}

        def env_int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        def env_float(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
        api_base = os.getenv("OPENAI_API_BASE", "").strip()
        if provider == "deepseek" and not api_base:
            api_base = "https://api.deepseek.com"
        device = env_int("AUDIO_DEVICE", -1)
        return cls(
            audio_source=os.getenv("AUDIO_MODE", "loopback"),
            audio_device=None if device < 0 else device,
            vad_threshold=env_float("VAD_ENERGY_THRESHOLD", 100.0),
            vad_adaptive=env_bool("VAD_ADAPTIVE", False),
            silence_seconds=env_float("SILENCE_DURATION", 1.5),
            min_speech_seconds=env_float("MIN_SPEECH_DURATION", 0.8),
            stt_provider=os.getenv("STT_PROVIDER", "xunfei"),
            stt_language=os.getenv("STT_LANGUAGE", "zh"),
            stt_model=os.getenv("STT_MODEL", "whisper-1"),
            local_whisper_model=os.getenv("LOCAL_WHISPER_MODEL", "medium"),
            local_whisper_device=os.getenv("LOCAL_WHISPER_DEVICE", "cpu"),
            llm_provider=provider,
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            llm_api_base=api_base,
            llm_thinking_enabled=env_bool("LLM_THINKING_ENABLED", False),
            llm_temperature=env_float("LLM_TEMPERATURE", 0.7),
            llm_max_tokens=env_int("LLM_MAX_TOKENS", 1024),
            max_history=env_int("MAX_HISTORY", 5),
            system_prompt=os.getenv("SYSTEM_PROMPT", ""),
            self_intro=os.getenv("SELF_INTRO", ""),
            enable_tts=env_bool("ENABLE_TTS", False),
            overlay_width=env_int("OVERLAY_WIDTH", 760),
            overlay_height=env_int("OVERLAY_HEIGHT", 560),
            overlay_font_size=env_int("OVERLAY_FONT_SIZE", 20),
            overlay_opacity=env_float("OVERLAY_OPACITY", 0.96),
            overlay_always_on_top=env_bool("OVERLAY_ALWAYS_ON_TOP", True),
        ).normalized()
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AppSettings":
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in values.items() if key in known}).normalized()


@dataclass
class Secrets:
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    iflytek_app_id: str = ""
    iflytek_api_key: str = ""
    iflytek_api_secret: str = ""


@dataclass
class Exchange:
    id: int
    session_id: str
    question: str
    answer: str
    created_at: str
    latency_ms: int


@dataclass
class LogRecordData:
    timestamp: str
    level: str
    source: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)
