from __future__ import annotations

from PySide6.QtTest import QSignalSpy

from interview_assistant.history import HistoryStore
from interview_assistant.models import AppSettings, Secrets
from interview_assistant.pipeline import PipelineThread


def test_quick_response_pipeline(qapp, workspace_tmp):
    history = HistoryStore(workspace_tmp / "history.db")
    session_id = history.start_session("loopback", "deepseek-chat")
    settings = AppSettings(
        self_intro="面试官你好，我是测试候选人。",
        history_enabled=True,
    )
    pipeline = PipelineThread(
        settings,
        Secrets(),
        "",
        session_id,
        history,
    )
    completed = QSignalSpy(pipeline.answer_completed)
    saved = QSignalSpy(pipeline.exchange_saved)
    pipeline._handle_question("请先做个自我介绍")
    assert completed.count() == 1
    assert completed.at(0)[0] == "面试官你好，我是测试候选人。"
    assert saved.count() == 1
    rows = history.list_exchanges()
    assert len(rows) == 1
    assert rows[0].answer == "面试官你好，我是测试候选人。"

def test_streaming_answer_pipeline(qapp, workspace_tmp, monkeypatch):
    history = HistoryStore(workspace_tmp / "pipeline-stream.db")
    session_id = history.start_session("loopback", "deepseek-chat")
    settings = AppSettings(history_enabled=True)
    pipeline = PipelineThread(settings, Secrets(), "", session_id, history)

    class FakeLlm:
        def __init__(self, *_args, **_kwargs):
            pass

        def ask_stream(self, _question, _history, on_delta, _cancel_event):
            on_delta("第一段")
            on_delta("，第二段。")
            return "第一段，第二段。"

    monkeypatch.setattr("interview_assistant.pipeline.LlmClient", FakeLlm)
    completed = QSignalSpy(pipeline.answer_completed)
    deltas = QSignalSpy(pipeline.answer_delta)
    pipeline._handle_question("请说明线程和进程的区别")
    assert completed.count() == 1
    assert completed.at(0)[0] == "第一段，第二段。"
    assert deltas.count() == 2
    assert history.list_exchanges()[0].answer == "第一段，第二段。"


def test_stop_does_not_discard_last_recognized_question(qapp, workspace_tmp):
    history = HistoryStore(workspace_tmp / "pipeline-stop.db")
    session_id = history.start_session("mic", "deepseek-chat")
    settings = AppSettings(self_intro="\u81ea\u6211\u4ecb\u7ecd\u56de\u7b54", history_enabled=False)
    pipeline = PipelineThread(settings, Secrets(), "", session_id, history)
    completed = QSignalSpy(pipeline.answer_completed)
    questions = QSignalSpy(pipeline.question_final)
    pipeline._stop_event.set()
    pipeline._handle_question("\u8bf7\u5148\u505a\u4e2a\u81ea\u6211\u4ecb\u7ecd")
    assert questions.count() == 1
    assert completed.count() == 1
    assert completed.at(0)[0] == "\u81ea\u6211\u4ecb\u7ecd\u56de\u7b54"
