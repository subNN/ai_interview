from __future__ import annotations

from types import SimpleNamespace

import interview_assistant.core.llm as llm_module
from interview_assistant.core.llm import LlmClient
from interview_assistant.models import AppSettings, Secrets


def test_llm_client_falls_back_to_v1_and_non_stream(monkeypatch):
    calls = []

    class FakeCompletions:
        def __init__(self, base_url):
            self.base_url = base_url

        def create(self, **kwargs):
            calls.append((self.base_url, kwargs["stream"]))
            if self.base_url == "http://127.0.0.1:7863":
                raise RuntimeError("Error code: 404")
            if kwargs["stream"]:
                return []
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="fallback answer")
                    )
                ]
            )

    class FakeChat:
        def __init__(self, base_url):
            self.completions = FakeCompletions(base_url)

    class FakeOpenAI:
        def __init__(self, api_key, timeout, base_url=None):
            assert api_key == "test-key"
            self.chat = FakeChat(base_url)

    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    settings = AppSettings(
        llm_provider="deepseek",
        llm_model="cn:deepseek-v4-flash",
        llm_api_base="http://127.0.0.1:7863",
    )
    client = LlmClient(settings, Secrets(deepseek_api_key="test-key"), "system")
    deltas = []
    answer = client.ask_stream(
        "question",
        [],
        deltas.append,
        __import__("threading").Event(),
    )
    assert answer == "fallback answer"
    assert deltas == ["fallback answer"]
    assert calls == [
        ("http://127.0.0.1:7863", True),
        ("http://127.0.0.1:7863", False),
        ("http://127.0.0.1:7863", True),
        ("http://127.0.0.1:7863", False),
        ("http://127.0.0.1:7863/v1", True),
        ("http://127.0.0.1:7863/v1", False),
    ]



def test_llm_defaults_to_fast_mode_without_deep_thinking(monkeypatch):
    seen = []

    class FakeCompletions:
        def create(self, **kwargs):
            seen.append(kwargs)
            return [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="fast", reasoning_content=None)
                        )
                    ]
                )
            ]

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, api_key, timeout, base_url=None):
            self.chat = FakeChat()

    monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)
    settings = AppSettings(
        llm_provider="deepseek",
        llm_model="cn:deepseek-v4-flash",
        llm_api_base="http://127.0.0.1:7863",
        llm_thinking_enabled=False,
    )
    client = LlmClient(settings, Secrets(deepseek_api_key="test-key"), "system")
    answer = client.ask_stream(
        "question", [], lambda _text: None, __import__("threading").Event()
    )
    assert answer == "fast"
    assert seen[0]["reasoning_effort"] == "none"
    assert seen[0]["extra_body"]["thinking"] == {"type": "disabled"}
    assert seen[0]["extra_body"]["enable_thinking"] is False
