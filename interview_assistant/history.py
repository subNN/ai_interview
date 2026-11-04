from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .models import Exchange


class HistoryStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._lock, closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    audio_source TEXT NOT NULL,
                    model TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_exchanges_created_at
                ON exchanges(created_at DESC);
                """
            )
            connection.commit()

    def start_session(self, audio_source: str, model: str) -> str:
        session_id = uuid4().hex
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO sessions(id, started_at, audio_source, model) VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    datetime.now().isoformat(timespec="seconds"),
                    audio_source,
                    model,
                ),
            )
            connection.commit()
        return session_id

    def end_session(self, session_id: str):
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), session_id),
            )
            connection.commit()

    def add_exchange(
        self,
        session_id: str,
        question: str,
        answer: str,
        latency_ms: int,
    ) -> int:
        with self._lock, closing(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO exchanges(session_id, question, answer, created_at, latency_ms)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    question,
                    answer,
                    datetime.now().isoformat(timespec="seconds"),
                    max(0, int(latency_ms)),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_exchanges(self, search: str = "", limit: int = 100) -> list[Exchange]:
        query = """
            SELECT id, session_id, question, answer, created_at, latency_ms
            FROM exchanges
        """
        params: list[object] = []
        if search.strip():
            query += " WHERE question LIKE ? OR answer LIKE ?"
            term = f"%{search.strip()}%"
            params.extend([term, term])
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            Exchange(
                id=row["id"],
                session_id=row["session_id"],
                question=row["question"],
                answer=row["answer"],
                created_at=row["created_at"],
                latency_ms=row["latency_ms"],
            )
            for row in rows
        ]

    def count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM exchanges").fetchone()
        return int(row["count"] if row else 0)

    def clear(self):
        with self._lock, closing(self._connect()) as connection:
            connection.execute("DELETE FROM exchanges")
            connection.execute("DELETE FROM sessions")
            connection.commit()
