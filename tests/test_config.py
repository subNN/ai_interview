from __future__ import annotations

import json

from interview_assistant.config import ConfigManager
from interview_assistant.models import AppSettings, Secrets


class MemorySecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str:
        return self.values.get(name, "")

    def set(self, name: str, value: str) -> bool:
        self.values[name] = value
        return True


def test_settings_normalization():
    settings = AppSettings(
        overlay_opacity=0.1,
        overlay_font_size=100,
        overlay_width=10,
        silence_seconds=0,
        llm_temperature=5,
    ).normalized()
    assert settings.overlay_opacity == 0.65
    assert settings.overlay_font_size == 32
    assert settings.overlay_width == 560
    assert settings.silence_seconds == 0.5
    assert settings.llm_temperature == 2.0


def test_config_does_not_write_secrets(workspace_tmp):
    store = MemorySecretStore()
    manager = ConfigManager(workspace_tmp, secret_store=store)
    settings = AppSettings(overlay_opacity=0.82)
    secrets = Secrets(
        deepseek_api_key="test-deepseek-key",
        openai_api_key="test-openai-key",
        iflytek_app_id="app",
        iflytek_api_key="ifly-key",
        iflytek_api_secret="ifly-secret",
    )
    failed = manager.save(settings, secrets)
    assert failed == []
    config_text = manager.config_path.read_text(encoding="utf-8")
    data = json.loads(config_text)
    assert data["settings"]["overlay_opacity"] == 0.82
    assert "test-deepseek-key" not in config_text
    assert store.values["deepseek_api_key"] == "test-deepseek-key"
