from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    def __init__(self, app, callbacks: dict[int, Callable[[], None]], logger=None):
        super().__init__()
        self.app = app
        self.callbacks = callbacks
        self.logger = logger
        self.available = sys.platform == "win32"
        self._registered: set[int] = set()
        if self.available:
            app.installNativeEventFilter(self)

    def register_defaults(self) -> bool:
        if not self.available:
            return False
        bindings = {
            1: (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x20),
            2: (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x48),
            3: (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x4C),
        }
        for hotkey_id, (modifiers, virtual_key) in bindings.items():
            if ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
                self._registered.add(hotkey_id)
            elif self.logger:
                self.logger.warning("全局快捷键 %s 注册失败，可能已被其他程序占用", hotkey_id)
        return bool(self._registered)

    def nativeEventFilter(self, event_type, message):
        if not self.available or bytes(event_type) not in (
            b"windows_generic_MSG",
            b"windows_dispatcher_MSG",
        ):
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message != WM_HOTKEY:
            return False, 0
        callback = self.callbacks.get(int(msg.wParam))
        if callback is None:
            return False, 0
        callback()
        return True, 0

    def unregister_all(self):
        if not self.available:
            return
        for hotkey_id in list(self._registered):
            try:
                ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._registered.clear()
        try:
            self.app.removeNativeEventFilter(self)
        except Exception:
            pass
