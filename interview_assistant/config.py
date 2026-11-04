from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .models import AppSettings, Secrets


APP_NAME = "InterviewAssistant"
KEYRING_SERVICE = "InterviewAssistant"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root()


def resource_path(name: str) -> Path:
    return project_root() / name


def app_config_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


class SecretStore:
    """Use Windows Credential Manager through keyring, with env as read-only fallback."""

    ENV_NAMES = {
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "iflytek_app_id": "IFLYTEK_APP_ID",
        "iflytek_api_key": "IFLYTEK_API_KEY",
        "iflytek_api_secret": "IFLYTEK_API_SECRET",
    }

    def __init__(self):
        self._memory: dict[str, str] = {}
        self._keyring = None
        try:
            import keyring

            self._keyring = keyring
        except Exception:
            pass

    def get(self, name: str) -> str:
        if name in self._memory:
            return self._memory[name]
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(KEYRING_SERVICE, name)
                if value:
                    self._memory[name] = value
                    return value
            except Exception:
                pass
        return os.getenv(self.ENV_NAMES.get(name, name), "")

    def set(self, name: str, value: str) -> bool:
        value = value.strip()
        self._memory[name] = value
        if not value:
            if self._keyring is not None:
                try:
                    self._keyring.delete_password(KEYRING_SERVICE, name)
                except Exception:
                    pass
            return True
        if self._keyring is None:
            return False
        try:
            self._keyring.set_password(KEYRING_SERVICE, name, value)
            return True
        except Exception:
            return False


class ConfigManager:
    SECRET_FIELDS = (
        "deepseek_api_key",
        "openai_api_key",
        "iflytek_app_id",
        "iflytek_api_key",
        "iflytek_api_secret",
    )

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        secret_store: Optional[SecretStore] = None,
    ):
        self.config_dir = config_dir or app_config_dir()
        self.config_path = self.config_dir / "config.json"
        self.secret_store = secret_store or SecretStore()

    def load(self) -> tuple[AppSettings, Secrets, bool]:
        load_dotenv(resource_path(".env"), override=False)
        load_dotenv(application_dir() / ".env", override=False)
        is_new = not self.config_path.exists()
        if self.config_path.exists():
            try:
                values = json.loads(self.config_path.read_text(encoding="utf-8"))
                settings = AppSettings.from_dict(values.get("settings", values))
            except Exception:
                settings = AppSettings.from_env()
                is_new = True
        else:
            settings = AppSettings.from_env()

        secrets = Secrets(
            **{
                name: self.secret_store.get(name)
                for name in self.SECRET_FIELDS
            }
        )
        return settings, secrets, is_new

    def save_settings(self, settings: AppSettings):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "settings": settings.normalized().to_dict(),
        }
        temp_path = self.config_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.config_path)

    def save(self, settings: AppSettings, secrets: Secrets) -> list[str]:
        self.save_settings(settings)
        failed: list[str] = []
        for name in self.SECRET_FIELDS:
            if not self.secret_store.set(name, getattr(secrets, name, "")):
                failed.append(name)
        return failed


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _default_settings_from_env() -> AppSettings:
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    api_base = os.getenv("OPENAI_API_BASE", "").strip()
    if provider == "deepseek" and not api_base:
        api_base = "https://api.deepseek.com"
    device = _env_int("AUDIO_DEVICE", -1)
    return AppSettings(
        audio_source=os.getenv("AUDIO_MODE", "loopback"),
        audio_device=None if device < 0 else device,
        vad_threshold=_env_float("VAD_ENERGY_THRESHOLD", 100.0),
        vad_adaptive=_env_bool("VAD_ADAPTIVE", False),
        silence_seconds=_env_float("SILENCE_DURATION", 1.5),
        min_speech_seconds=_env_float("MIN_SPEECH_DURATION", 0.8),
        stt_provider=os.getenv("STT_PROVIDER", "xunfei"),
        stt_language=os.getenv("STT_LANGUAGE", "zh"),
        stt_model=os.getenv("STT_MODEL", "whisper-1"),
        local_whisper_model=os.getenv("LOCAL_WHISPER_MODEL", "medium"),
        local_whisper_device=os.getenv("LOCAL_WHISPER_DEVICE", "cpu"),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
        llm_api_base=api_base,
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.7),
        llm_max_tokens=_env_int("LLM_MAX_TOKENS", 1024),
        max_history=_env_int("MAX_HISTORY", 5),
        system_prompt=os.getenv("SYSTEM_PROMPT", ""),
        self_intro=os.getenv("SELF_INTRO", ""),
        enable_tts=_env_bool("ENABLE_TTS", False),
        overlay_width=_env_int("OVERLAY_WIDTH", 760),
        overlay_height=_env_int("OVERLAY_HEIGHT", 560),
        overlay_font_size=_env_int("OVERLAY_FONT_SIZE", 20),
        overlay_opacity=_env_float("OVERLAY_OPACITY", 0.96),
        overlay_always_on_top=_env_bool("OVERLAY_ALWAYS_ON_TOP", True),
    ).normalized()



