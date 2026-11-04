from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from interview_assistant.ui.overlay import TitleBar


class FakeHandle:
    def __init__(self, system_move_result: bool):
        self.system_move_result = system_move_result

    def startSystemMove(self):
        return self.system_move_result


class FakeWindow:
    def __init__(self, system_move_result: bool):
        self._handle = FakeHandle(system_move_result)
        self.moves: list[QPoint] = []

    def windowHandle(self):
        return self._handle

    def pos(self):
        return QPoint(50, 50)

    def move(self, point):
        self.moves.append(QPoint(point))


class ProbeTitleBar(TitleBar):
    def __init__(self, window):
        super().__init__()
        self._fake_window = window

    def window(self):
        return self._fake_window


def _mouse_event(event_type, global_x, global_y, buttons=Qt.MouseButton.LeftButton):
    return QMouseEvent(
        event_type,
        QPointF(10, 10),
        QPointF(global_x, global_y),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_native_move_does_not_apply_manual_offset(qapp):
    window = FakeWindow(system_move_result=True)
    title = ProbeTitleBar(window)
    title.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, 100, 100))
    title.mouseMoveEvent(_mouse_event(QEvent.Type.MouseMove, 140, 150))
    assert window.moves == []
    assert title._native_move is True


def test_fallback_move_uses_fixed_window_origin(qapp):
    window = FakeWindow(system_move_result=False)
    title = ProbeTitleBar(window)
    title.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, 100, 100))
    title.mouseMoveEvent(_mouse_event(QEvent.Type.MouseMove, 130, 140))
    title.mouseMoveEvent(_mouse_event(QEvent.Type.MouseMove, 150, 160))
    assert window.moves[-2] == QPoint(80, 90)
    assert window.moves[-1] == QPoint(100, 110)
