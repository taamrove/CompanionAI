"""Append-only audit log for every self-improvement action.

Plain JSONL on disk — tamper-evident enough for a personal system and trivial
to inspect. The kernel writes; nothing in userland can rewrite history.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, action: str, skill: str, **fields) -> dict:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "skill": skill,
            **fields,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        return entry

    def tail(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for ln in lines[-limit:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
