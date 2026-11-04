from __future__ import annotations

from interview_assistant.history import HistoryStore
from interview_assistant.models import AppSettings, Secrets
from interview_assistant.ui.main_window import MainWindow
from interview_assistant.ui.overlay import OverlayWindow
from interview_assistant.ui.theme import apply_theme


def test_overlay_runtime_controls(qtbot, qapp, workspace_tmp):
    apply_theme(qapp)
    settings = AppSettings(overlay_font_size=20, overlay_opacity=0.96)
    overlay = OverlayWindow(settings)
    qtbot.addWidget(overlay)
    overlay.show()
    qtbot.wait(30)

    overlay.begin_question()
    overlay.set_question("测试问题")
    overlay.begin_answer()
    overlay.append_answer("测试回答")
    assert overlay._answer_text.toPlainText() == "测试回答"
    assert len(overlay._resize_handles) == 8

    overlay.change_font_size(2)
    assert overlay._font_size == 22
    overlay._opacity_slider.setValue(80)
    assert abs(overlay.windowOpacity() - 0.8) < 0.02
    overlay.resize(900, 640)
    assert overlay.width() == 900
    assert overlay.height() == 640
    overlay.shutdown_ui()


def test_main_window_builds(qtbot, qapp, workspace_tmp):
    apply_theme(qapp)
    history = HistoryStore(workspace_tmp / "history.db")
    window = MainWindow(AppSettings(), Secrets(), history)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)
    assert window.stack.count() == 4
    assert window.live_page.start_button.isEnabled()
    window.force_close()
