"""Versioned storage for a single skill, with a last-known-good pointer.

Each skill keeps an append-only list of immutable versions plus pointers:
  * active          — the version currently in use
  * last_known_good — the most recent version that booted & passed health
  * staged          — a version queued to apply on the next restart
  * boot_attempt    — crash sentinel: the version we're promoting this boot
                      (cleared once boot is confirmed; if still set next boot,
                      that version crashed → roll back)

Everything lives under ``<DATA_DIR>/skills/<name>/`` so the shipped baseline in
``skills/`` (git, human-owned) is never mutated by the runtime.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class VersionStore:
    def __init__(self, root: Path, name: str) -> None:
        self.name = name
        self.dir = root / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        if not self.state_path.exists():
            self._write_state(
                {
                    "active": None,
                    "last_known_good": None,
                    "staged": None,
                    "boot_attempt": None,
                    "versions": [],
                }
            )

    # ── state helpers ───────────────────────────────────────────────
    def _state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _version_path(self, vid: int) -> Path:
        return self.dir / f"v{vid:04d}.json"

    # ── reads ───────────────────────────────────────────────────────
    @property
    def initialized(self) -> bool:
        return self._state()["active"] is not None

    def content(self, vid: int) -> str | None:
        p = self._version_path(vid)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["content"]

    def active_id(self) -> int | None:
        return self._state()["active"]

    def lkg_id(self) -> int | None:
        return self._state()["last_known_good"]

    def staged_id(self) -> int | None:
        return self._state().get("staged")

    def boot_attempt_id(self) -> int | None:
        return self._state().get("boot_attempt")

    def active_content(self) -> str | None:
        vid = self.active_id()
        return self.content(vid) if vid is not None else None

    def lkg_content(self) -> str | None:
        vid = self.lkg_id()
        return self.content(vid) if vid is not None else None

    def history(self) -> list[dict]:
        state = self._state()
        out = []
        for v in state["versions"]:
            out.append(
                {
                    **v,
                    "active": v["id"] == state["active"],
                    "last_known_good": v["id"] == state["last_known_good"],
                }
            )
        return out

    # ── writes ──────────────────────────────────────────────────────
    def add_version(self, content: str, author: str, reason: str) -> int:
        state = self._state()
        vid = (max((v["id"] for v in state["versions"]), default=0)) + 1
        self._version_path(vid).write_text(
            json.dumps({"content": content}), encoding="utf-8"
        )
        state["versions"].append(
            {
                "id": vid,
                "author": author,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write_state(state)
        return vid

    def set_active(self, vid: int) -> None:
        state = self._state()
        state["active"] = vid
        self._write_state(state)

    def mark_known_good(self, vid: int) -> None:
        state = self._state()
        state["last_known_good"] = vid
        self._write_state(state)

    def set_staged(self, vid: int | None) -> None:
        state = self._state()
        state["staged"] = vid
        self._write_state(state)

    def set_boot_attempt(self, vid: int | None) -> None:
        state = self._state()
        state["boot_attempt"] = vid
        self._write_state(state)

    def seed(self, content: str) -> int:
        """First-time seed: version 1, active and known-good."""
        vid = self.add_version(content, author="baseline", reason="shipped default")
        self.set_active(vid)
        self.mark_known_good(vid)
        return vid
