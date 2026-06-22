"""SQLite-backed memory store.

Holds three things:
  * conversation turns (chat history per session)
  * long-term memories (facts the companion chose to remember)
  * embeddings for memories, so RAG can recall the relevant ones

Embeddings are stored as raw float bytes in the same row; similarity search is
done in Python (fine for a personal-scale dataset). Each memory is also mirrored
into the Markdown vault.
"""

from __future__ import annotations

import array
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.memory.vault import Vault


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pack(vec: list[float]) -> bytes:
    return array.array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(blob)
    return list(a)


class MemoryStore:
    def __init__(self, db_path: Path, vault_root: Path) -> None:
        self.db_path = db_path
        self.vault = Vault(vault_root)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session
                    ON turns (session_id, id);

                CREATE TABLE IF NOT EXISTS memories (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    kind       TEXT NOT NULL DEFAULT 'fact',
                    text       TEXT NOT NULL,
                    vault_path TEXT,
                    embedding  BLOB,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mem_session
                    ON memories (session_id);
                """
            )
            self._conn.commit()

    # ── conversation history ────────────────────────────────────────
    def add_turn(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, _now()),
            )
            self._conn.commit()

    def recent_turns(self, session_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM turns WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ── long-term memories ──────────────────────────────────────────
    def add_memory(
        self,
        session_id: str,
        text: str,
        kind: str = "fact",
        embedding: list[float] | None = None,
        tags: list[str] | None = None,
    ) -> int:
        vault_path = self.vault.write_note(kind, text, tags)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO memories "
                "(session_id, kind, text, vault_path, embedding, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    kind,
                    text,
                    vault_path,
                    _pack(embedding) if embedding else None,
                    _now(),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def all_memories(self, session_id: str | None = None) -> list[dict]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    "SELECT id, text, kind, vault_path, embedding "
                    "FROM memories WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, text, kind, vault_path, embedding FROM memories"
                ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "text": r["text"],
                    "kind": r["kind"],
                    "vault_path": r["vault_path"],
                    "embedding": _unpack(r["embedding"]) if r["embedding"] else None,
                }
            )
        return out
