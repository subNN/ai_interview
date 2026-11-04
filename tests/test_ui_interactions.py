from __future__ import annotations

import logging

from PySide6.QtTest import QSignalSpy

from interview_assistant.config import ConfigManager
from interview_assistant.controller import ApplicationController
from interview_assistant.history import HistoryStore
from interview_assistant.models import AppSettings, Secrets
from interview_assistant.ui.main_window import MainWindow
from interview_assistant.ui.overlay import OverlayWindow
from interview_assistant.ui.setup_wizard import SetupWizard
from interview_assistant.ui.theme import apply_theme


def test_main_window_session_actions(qtbot, qapp, workspace_tmp):
    apply_theme(qapp)
    window = MainWindow(
        AppSettings(),
        Secrets(),
        HistoryStore(workspace_tmp / "history.db"),
    )
    qtbot.addWidget(window)
    assert not window.settings_page.llm_thinking_enabled.isChecked()
    start_spy = QSignalSpy(window.start_requested)
    stop_spy = QSignalSpy(window.stop_requested)
    cancel_spy = QSignalSpy(window.cancel_requested)
    window.live_page.start_button.click()
    assert start_spy.count() == 1
    window.live_page.set_active(True)
    window.live_page.start_button.click()
    assert stop_spy.count() == 1
    window.live_page.set_state("generating", "正在生成回答")
    assert not window.live_page.cancel_button.isHidden()
    window.live_page.cancel_button.click()
    assert cancel_spy.count() == 1


def test_overlay_emits_appearance_changes(qtbot, qapp):
    apply_theme(qapp)
    overlay = OverlayWindow(AppSettings())
    qtbot.addWidget(overlay)
    opacity_spy = QSignalSpy(overlay.opacity_changed)
    font_spy = QSignalSpy(overlay.font_size_changed)
    overlay._opacity_slider.setValue(75)
    overlay.change_font_size(2)
    assert opacity_spy.count() == 1
    assert font_spy.count() == 1
    overlay.shutdown_ui()


def test_setup_wizard_values(qtbot, qapp, workspace_tmp):
    apply_theme(qapp)
    wizard = SetupWizard(AppSettings(), Secrets())
    qtbot.addWidget(wizard)
    assert len(wizard.pageIds()) == 4
    wizard.llm_model.setText("deepseek-chat")
    wizard.deepseek_key.setText("test-key")
    wizard.overlay_opacity.setValue(80)
    settings, secrets = wizard.values()
    assert settings.llm_model == "deepseek-chat"
    assert secrets.deepseek_api_key == "test-key"
    assert abs(settings.overlay_opacity - 0.8) < 0.01


def test_controller_blocks_missing_key(qapp, workspace_tmp):
    config = ConfigManager(workspace_tmp, secret_store=SecretsOnlyStore())
    history = HistoryStore(workspace_tmp / "history.db")
    controller = ApplicationController(
        config,
        history,
        AppSettings(),
        Secrets(),
        logging.getLogger("test-controller"),
        parent=qapp,
    )
    error_spy = QSignalSpy(controller.events.error)
    controller.start_session()
    assert error_spy.count() == 1
    assert not controller.is_active
    controller.shutdown()


class SecretsOnlyStore:
    def get(self, name):
        return ""

    def set(self, name, value):
        return True


def test_model_fetch_helpers(monkeypatch):
    import json

    from interview_assistant.ui import pages

    assert pages._model_api_urls("https://api.example.com") == [
        "https://api.example.com/models",
        "https://api.example.com/v1/models",
    ]
    assert pages._model_api_urls("https://api.example.com/v1") == [
        "https://api.example.com/v1/models"
    ]
    assert pages._extract_model_ids(
        {"data": [{"id": "model-a"}, {"id": "model-b"}, {"id": "model-a"}]}
    ) == ["model-a", "model-b"]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "model-a"}, {"id": "model-b"}]}).encode()

    def fake_urlopen(request, **_kwargs):
        assert request.full_url == "https://api.example.com/models"
        assert request.get_header("Authorization") == "Bearer test-key"
        return FakeResponse()

    monkeypatch.setattr(pages.urlrequest, "urlopen", fake_urlopen)
    assert pages._fetch_model_ids("https://api.example.com", "test-key") == [
        "model-a",
        "model-b",
    ]



def test_ai_test_helpers(monkeypatch):
    import json

    from interview_assistant.ui import pages

    assert pages._chat_completion_urls("https://api.example.com") == [
        "https://api.example.com/chat/completions",
        "https://api.example.com/v1/chat/completions",
    ]
    assert pages._chat_completion_urls("https://api.example.com/v1") == [
        "https://api.example.com/v1/chat/completions"
    ]
    assert pages._extract_ai_reply(
        {"choices": [{"message": {"content": "OK"}}]}
    ) == "OK"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "OK"}}]}
            ).encode()

    def fake_urlopen(request, **_kwargs):
        assert request.full_url == "https://api.example.com/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-key"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "model-a"
        assert payload["messages"][0]["content"] == "Reply with OK only."
        return FakeResponse()

    monkeypatch.setattr(pages.urlrequest, "urlopen", fake_urlopen)
    assert pages._test_ai_endpoint(
        "https://api.example.com", "test-key", "model-a"
    ) == "OK"
