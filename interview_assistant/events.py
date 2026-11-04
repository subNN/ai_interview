from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ApplicationEvents(QObject):
    state_changed = Signal(str, str)
    transcript_partial = Signal(str)
    question_final = Signal(str)
    answer_started = Signal(str)
    answer_delta = Signal(str)
    answer_completed = Signal(str, int)
    audio_level = Signal(float)
    error = Signal(str, str)
    session_active_changed = Signal(bool)
    exchange_saved = Signal()
    conversation_cleared = Signal()
