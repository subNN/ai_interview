from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal


_SECRET_PATTERNS = (
    re.compile(r"(Authorization\s*[:=]\s*Bearer\s+)[^\s,;]+", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret|token)\s*[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+"),
)


def redact_sensitive(text: str) -> str:
    result = str(text)
    result = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", result)
    result = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", result)
    result = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", result)
    return result


class LogBridge(QObject):
    record_emitted = Signal(object)

    def __init__(self):
        super().__init__()
        self.records: list[dict] = []

    def publish(self, record: dict):
        self.records.append(record)
        if len(self.records) > 2500:
            del self.records[:500]
        self.record_emitted.emit(record)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive(super().format(record))


class SignalLogHandler(logging.Handler):
    def __init__(self, bridge: LogBridge):
        super().__init__()
        self.bridge = bridge

    def emit(self, record: logging.LogRecord):
        try:
            message = redact_sensitive(record.getMessage())
            self.bridge.record_emitted.emit(
                {
                    "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                    "level": record.levelname,
                    "source": record.name.rsplit(".", 1)[-1],
                    "message": message,
                }
            )
        except Exception:
            self.handleError(record)


def setup_logging(
    log_dir: Path,
    debug_console: bool = False,
    retention_days: int = 14,
) -> tuple[LogBridge, logging.Logger]:
    log_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - max(1, retention_days) * 86400
    for old_log in log_dir.glob("app.log*"):
        try:
            if old_log.stat().st_mtime < cutoff:
                old_log.unlink()
        except OSError:
            pass
    logger = logging.getLogger("interview_assistant")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_interview_assistant", False):
            logger.removeHandler(handler)
            handler.close()

    bridge = LogBridge()
    formatter = RedactingFormatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler._interview_assistant = True
    logger.addHandler(file_handler)

    ui_handler = SignalLogHandler(bridge)
    ui_handler._interview_assistant = True
    logger.addHandler(ui_handler)

    if debug_console or sys.stdout:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler._interview_assistant = True
        logger.addHandler(stream_handler)

    return bridge, logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    return logging.getLogger(f"interview_assistant.{name}" if name else "interview_assistant")
