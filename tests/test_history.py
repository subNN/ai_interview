from __future__ import annotations

from interview_assistant.history import HistoryStore


def test_history_round_trip(workspace_tmp):
    store = HistoryStore(workspace_tmp / "history.db")
    session_id = store.start_session("loopback", "deepseek-chat")
    exchange_id = store.add_exchange(
        session_id,
        "如何设计高可用系统？",
        "通过超时、重试和降级保证可用性。",
        1280,
    )
    rows = store.list_exchanges()
    assert exchange_id > 0
    assert len(rows) == 1
    assert rows[0].question.startswith("如何设计")
    assert rows[0].latency_ms == 1280
    assert store.count() == 1

    store.clear()
    assert store.list_exchanges() == []
