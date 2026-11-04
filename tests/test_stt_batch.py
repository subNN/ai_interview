from __future__ import annotations

import json

import websocket

from interview_assistant.core.stt import SttEngine
from interview_assistant.models import AppSettings, Secrets


def test_xunfei_batch_uses_final_status_on_last_audio_chunk(monkeypatch):
    sent = []

    class FakeWebSocket:
        def send(self, payload):
            sent.append(json.loads(payload))

        def recv(self):
            return json.dumps(
                {
                    "code": 0,
                    "data": {
                        "status": 2,
                        "result": {"ws": [{"cw": [{"w": "\u6d4b\u8bd5\u95ee\u9898"}]}]},
                    },
                }
            )

        def close(self):
            pass

    monkeypatch.setattr(websocket, "create_connection", lambda *_args, **_kwargs: FakeWebSocket())
    monkeypatch.setattr(SttEngine, "_xunfei_url", lambda self: "wss://example.invalid")
    settings = AppSettings(stt_provider="xunfei", stt_language="zh")
    secrets = Secrets(
        iflytek_app_id="app",
        iflytek_api_key="key",
        iflytek_api_secret="secret",
    )
    text = SttEngine(settings, secrets)._transcribe_xunfei_batch(b"a" * 2560)
    assert text == "\u6d4b\u8bd5\u95ee\u9898"
    assert [item["data"]["status"] for item in sent] == [0, 2]
    assert all(item["data"].get("audio") for item in sent)
