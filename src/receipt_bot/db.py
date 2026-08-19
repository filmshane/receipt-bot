from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_id INTEGER PRIMARY KEY,
                    updated_at TEXT,
                    state_json TEXT
                );
                CREATE TABLE IF NOT EXISTS pending (
                    chat_id INTEGER PRIMARY KEY,
                    partial_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def is_processed(self, chat_id: int, message_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM processed_messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id),
            )
            return cur.fetchone() is not None

    def mark_processed(self, chat_id: int, message_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages (chat_id, message_id) VALUES (?, ?)",
                (chat_id, message_id),
            )

    def set_pending(self, chat_id: int, data: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending (chat_id, partial_json) VALUES (?, ?)",
                (chat_id, json.dumps(data)),
            )

    def get_pending(self, chat_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT partial_json FROM pending WHERE chat_id=?", (chat_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return json.loads(row["partial_json"])

    def clear_pending(self, chat_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pending WHERE chat_id=?", (chat_id,))

    def append_session_turn(self, chat_id: int, role: str, content: str, max_turns: int = 12) -> None:
        with self.connect() as conn:
            cur = conn.execute("SELECT state_json FROM sessions WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
            state = json.loads(row["state_json"]) if row and row["state_json"] else {"turns": []}
            turns = state.get("turns") or []
            turns.append({"role": role, "content": content})
            state["turns"] = turns[-max_turns:]
            conn.execute(
                "INSERT OR REPLACE INTO sessions (chat_id, updated_at, state_json) VALUES (?, datetime('now'), ?)",
                (chat_id, json.dumps(state)),
            )

    def get_turns(self, chat_id: int) -> list:
        with self.connect() as conn:
            cur = conn.execute("SELECT state_json FROM sessions WHERE chat_id=?", (chat_id,))
            row = cur.fetchone()
            if not row or not row["state_json"]:
                return []
            return json.loads(row["state_json"]).get("turns") or []
