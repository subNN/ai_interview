from __future__ import annotations

import argparse
import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from .config import ConfigManager, app_data_dir
from .controller import ApplicationController
from .history import HistoryStore
from .logging_utils import get_logger, setup_logging
from .models import SessionState
from .platform.hotkeys import GlobalHotkeyManager
from .ui.icons import app_icon
from .ui.main_window import MainWindow
from .ui.overlay import OverlayWindow
from .ui.setup_wizard import SetupWizard
from .ui.theme import apply_theme


def _set_windows_app_id():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "InterviewAssistant.Desktop.1"
            )
        except Exception:
            pass


def _ensure_debug_console():
    if sys.platform != "win32" or sys.stdout is not None:
        return
    try:
        ctypes.windll.kernel32.AllocConsole()
        ctypes.windll.kernel32.SetConsoleTitleW("AI 面试助手调试控制台")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stdin = open("CONIN$", "r", encoding="utf-8", buffering=1)
    except Exception:
        pass


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--debug-console", action="store_true", help="显示原生调试控制台")
    args, qt_args = parser.parse_known_args(argv)
    if args.debug_console:
        _ensure_debug_console()

    _set_windows_app_id()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("AI 面试助手")
    app.setApplicationDisplayName("AI 面试助手")
    app.setOrganizationName("InterviewAssistant")
    app.setApplicationVersion("1.1.0")
    app.setWindowIcon(app_icon())
    apply_theme(app)

    config = ConfigManager()
    settings, secrets, is_new = config.load()
    data_dir = app_data_dir()
    log_bridge, logger = setup_logging(
        data_dir / "logs",
        debug_console=args.debug_console,
        retention_days=settings.log_retention_days,
    )
    history = HistoryStore(data_dir / "history.db")
    controller = ApplicationController(
        config,
        history,
        settings,
        secrets,
        logger,
        parent=app,
    )
    overlay = OverlayWindow(settings)
    main_window = MainWindow(settings, secrets, history)
    main_window.bind_events(controller.events)
    main_window.bind_log_bridge(log_bridge)

    def update_overlay_state(state: str, label: str):
        kind = {
            SessionState.LISTENING.value: "info",
            SessionState.RECOGNIZING.value: "working",
            SessionState.GENERATING.value: "working",
            SessionState.READY.value: "ready",
            SessionState.ERROR.value: "error",
            SessionState.IDLE.value: "info",
        }.get(state, "info")
        overlay.set_status(label, kind)

    def update_partial(text: str):
        if text:
            overlay.append_question_partial(text)
        else:
            overlay.begin_question()

    controller.events.state_changed.connect(update_overlay_state)
    controller.events.transcript_partial.connect(update_partial)
    controller.events.question_final.connect(overlay.set_question)
    controller.events.answer_started.connect(lambda _question: overlay.begin_answer())
    controller.events.answer_delta.connect(overlay.append_answer)
    controller.events.answer_completed.connect(
        lambda answer, _latency: overlay.set_answer(answer)
    )
    controller.events.error.connect(
        lambda title, detail: (
            overlay.set_status(title, "error"),
            main_window.notify_error(title, detail),
        )
    )
    controller.events.conversation_cleared.connect(overlay.clear_content)
    controller.events.conversation_cleared.connect(main_window.live_page.clear_content)

    main_window.start_requested.connect(controller.start_session)
    main_window.stop_requested.connect(controller.stop_session)
    main_window.manual_requested.connect(controller.manual_trigger)
    main_window.cancel_requested.connect(controller.cancel_answer)
    main_window.clear_requested.connect(controller.clear_conversation)
    main_window.overlay_requested.connect(overlay.show)
    main_window.settings_saved.connect(controller.save_settings)
    controller.settings_applied.connect(main_window.apply_settings)
    controller.settings_save_completed.connect(main_window.settings_saved_feedback)
    controller.settings_applied.connect(
        lambda updated, _secrets: (
            overlay.apply_settings(updated),
            overlay.set_meta(f"{updated.llm_provider.upper()} · {updated.audio_source}"),
        )
    )
    overlay.geometry_changed.connect(controller.persist_overlay_geometry)
    overlay.opacity_changed.connect(controller.persist_overlay_opacity)
    overlay.font_size_changed.connect(controller.persist_overlay_font_size)
    overlay.set_meta(f"{settings.llm_provider.upper()} · {settings.audio_source}")

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    tray = QSystemTrayIcon(app_icon(48), app)
    tray.setToolTip("AI 面试助手")
    tray_menu = QMenu()
    show_main_action = QAction("显示控制中心", app)
    show_overlay_action = QAction("显示悬浮窗", app)
    session_action = QAction("开始监听", app)
    quit_action = QAction("退出", app)
    tray_menu.addAction(show_main_action)
    tray_menu.addAction(show_overlay_action)
    tray_menu.addSeparator()
    tray_menu.addAction(session_action)
    tray_menu.addSeparator()
    tray_menu.addAction(quit_action)
    tray.setContextMenu(tray_menu)

    show_main_action.triggered.connect(
        lambda: (main_window.show(), main_window.raise_(), main_window.activateWindow())
    )
    show_overlay_action.triggered.connect(
        lambda: (overlay.show(), overlay.raise_())
    )
    session_action.triggered.connect(controller.toggle_session)
    tray.activated.connect(
        lambda reason: (
            main_window.show()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
    )
    if tray_available:
        tray.show()

    def update_tray_session(active: bool):
        session_action.setText("停止监听" if active else "开始监听")

    controller.events.session_active_changed.connect(update_tray_session)

    hotkeys = None
    exit_guard = {"done": False}
    cleanup_guard = {"done": False}

    def cleanup_application():
        if cleanup_guard["done"]:
            return
        cleanup_guard["done"] = True
        try:
            hotkeys.unregister_all()
        except Exception:
            pass
        controller.shutdown()
        overlay.shutdown_ui()
        tray.hide()

    def quit_application():
        if exit_guard["done"]:
            return
        exit_guard["done"] = True
        cleanup_application()
        main_window.force_close()
        app.quit()

    quit_action.triggered.connect(quit_application)
    app.aboutToQuit.connect(cleanup_application)

    def show_hidden_notice():
        if tray_available:
            tray.showMessage(
                "AI 面试助手",
                "控制中心已隐藏，可从系统托盘重新打开。",
                QSystemTrayIcon.MessageIcon.Information,
                2200,
            )
        else:
            quit_application()

    main_window.hide_to_tray.connect(show_hidden_notice)
    main_window.quit_requested.connect(quit_application)
    app.setQuitOnLastWindowClosed(False)

    hotkeys = GlobalHotkeyManager(
        app,
        {
            1: lambda: controller.manual_trigger()
            if controller.is_active
            else controller.start_session(),
            2: overlay.toggle_visible,
            3: controller.clear_conversation,
        },
        logger=get_logger("hotkeys"),
    )
    hotkeys.register_defaults()

    main_window.show_page(0)
    main_window.show()
    if is_new and not (secrets.deepseek_api_key or secrets.openai_api_key):
        wizard = SetupWizard(settings, secrets, main_window)
        if wizard.exec() == QDialog.DialogCode.Accepted:
            controller.save_settings(*wizard.values())
            logger.info("首次配置已完成")
        else:
            main_window.show_page(2)
            logger.info("首次配置已跳过，可在设置页继续配置")
    overlay.show()
    overlay.raise_()
    return app.exec()
