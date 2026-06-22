"""SkillRegistry — the kernel's guardian of userland behaviour.

The companion reads its mutable behaviour (persona, routing) *through* this
object. It is the only thing that activates a revision, and it enforces:

  * a master kill switch (``SELFIMPROVE_ENABLED``) the AI cannot flip
  * a health gate on every activation, with automatic rollback on failure
  * a runtime fallback chain so a bad/missing skill never halts the companion
  * an audit trail of every action
"""

from __future__ import annotations

import json
from pathlib import Path

from core.config import Settings
from core.selfimprove.audit import AuditLog
from core.selfimprove.health import run_check
from core.selfimprove.versioning import VersionStore
from core.trusted import is_mutable

# Ultimate, baked-in fallbacks — used only if every on-disk source is gone.
_BAKED_DEFAULTS = {
    "persona": "You are CompanionAI, a helpful, warm personal companion. "
    "Be concise and personable. Lead with the answer.",
    "routing": json.dumps({"length_threshold": 280, "heavy_hints": []}),
}
_EXT = {"persona": "md", "routing": "json"}


class SkillRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._runtime_root = settings.data_path / "skills"
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        self._shipped_root = settings.skills_path
        self.audit = AuditLog(settings.data_path / "audit.jsonl")
        self._stores: dict[str, VersionStore] = {}

    # ── config-driven gates ─────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        """Master kill switch. Human-only — lives in the kernel/config."""
        return self.settings.selfimprove_enabled

    @property
    def mode(self) -> str:
        return self.settings.selfimprove_mode  # "auto" | "propose"

    # ── store + seeding ─────────────────────────────────────────────
    def _shipped_default(self, name: str) -> str:
        path = self._shipped_root / name / f"active.{_EXT.get(name, 'txt')}"
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8")
        except OSError:
            pass
        return _BAKED_DEFAULTS.get(name, "")

    def _store(self, name: str) -> VersionStore:
        store = self._stores.get(name)
        if store is None:
            store = VersionStore(self._runtime_root, name)
            if not store.initialized:
                store.seed(self._shipped_default(name))
            self._stores[name] = store
        return store

    # ── the resilient read path ─────────────────────────────────────
    def load(self, name: str) -> str:
        """Return the active skill content, self-healing on any failure so the
        companion never stops functioning."""
        store = self._store(name)
        try:
            content = store.active_content()
            if content is not None:
                return content
        except Exception:
            content = None
        # active broken/missing → fall back and self-heal the pointer
        for source, value in (
            ("last_known_good", lambda: store.lkg_content()),
            ("shipped", lambda: self._shipped_default(name)),
            ("baked", lambda: _BAKED_DEFAULTS.get(name, "")),
        ):
            try:
                healed = value()
            except Exception:
                healed = None
            if healed:
                self.audit.record("auto_heal", name, fell_back_to=source)
                return healed
        return _BAKED_DEFAULTS.get(name, "")

    # ── the guarded write path (stage now, apply on restart) ────────
    def apply(self, name: str, content: str, author: str, reason: str) -> dict:
        """Revise a skill. Snapshots it, runs a pre-flight health check, and —
        in auto mode — STAGES it to apply on the next restart (it does not touch
        the live version). In propose mode it only queues for human approval."""
        if not self.enabled:
            self.audit.record("rejected", name, author=author, why="self-improve disabled")
            return {"staged": False, "reason": "self-improvement is disabled"}

        # Enforce the trust partition: the target must be in the mutable layer.
        if not is_mutable(f"skills/{name}"):
            self.audit.record("rejected", name, author=author, why="target in trusted root")
            return {"staged": False, "reason": "target is in the trusted root (human-only)"}

        ok, msg = run_check(name, content)
        vid = self._store(name).add_version(content, author, reason)
        if not ok:
            self.audit.record("health_failed", name, version=vid, author=author, detail=msg)
            return {"staged": False, "version": vid, "reason": f"health check failed: {msg}"}

        if self.mode == "propose":
            self.audit.record("proposed", name, version=vid, author=author, reason=reason)
            return {"staged": False, "proposed": True, "version": vid,
                    "reason": "queued for human approval (propose mode)"}

        return self._stage(name, vid, author)

    def promote(self, name: str, vid: int, author: str) -> dict:
        """Human-approve a proposed version → stage it for the next restart."""
        store = self._store(name)
        content = store.content(vid)
        if content is None:
            return {"staged": False, "reason": f"no such version: {vid}"}
        ok, msg = run_check(name, content)
        if not ok:
            self.audit.record("health_failed", name, version=vid, author=author, detail=msg)
            return {"staged": False, "reason": f"health check failed: {msg}"}
        return self._stage(name, vid, author)

    def _stage(self, name: str, vid: int, author: str) -> dict:
        self._store(name).set_staged(vid)
        self.audit.record("staged", name, version=vid, author=author)
        return {"staged": True, "version": vid, "applies_on": "restart"}

    # ── boot sequence (apply on restart, with crash rollback) ───────
    def boot(self) -> None:
        """Run at startup. Promotes any staged version, health-checks it, and
        rolls back to last-known-good if it fails or a prior boot crashed."""
        for name in _EXT:
            self._boot_skill(name)

    def _boot_skill(self, name: str) -> None:
        store = self._store(name)

        # Crash sentinel: a boot_attempt still set means the last boot activated
        # a version but never confirmed healthy startup → it crashed. Roll back.
        attempt = store.boot_attempt_id()
        if attempt is not None:
            lkg = store.lkg_id()
            if lkg is not None:
                store.set_active(lkg)
            store.set_staged(None)
            store.set_boot_attempt(None)
            self.audit.record("crash_rollback", name, failed_version=attempt, restored=lkg)
            return

        staged = store.staged_id()
        if staged is None:
            return  # nothing to apply this boot

        ok, msg = run_check(name, store.content(staged) or "")
        if not ok:
            # Bad staged version — discard it, leave the live version untouched.
            store.set_staged(None)
            self.audit.record("rolled_back_on_boot", name, failed_version=staged, detail=msg)
            return

        # Activate, but DON'T mark known-good yet — keep the sentinel until the
        # app confirms a healthy startup. last_known_good stays on the old good
        # version, so a crash now rolls back to it (not to this candidate).
        store.set_active(staged)
        store.set_boot_attempt(staged)
        store.set_staged(None)
        self.audit.record("activated_on_boot", name, version=staged)

    def confirm_boot(self) -> None:
        """Call once the app has fully started. Promotes the just-activated
        version to last-known-good and clears the crash sentinel."""
        for name in _EXT:
            store = self._store(name)
            attempt = store.boot_attempt_id()
            if attempt is not None:
                store.mark_known_good(attempt)
                store.set_boot_attempt(None)
                self.audit.record("boot_confirmed", name, version=attempt)

    def rollback(self, name: str, author: str, to: int | None = None) -> dict:
        store = self._store(name)
        target = to if to is not None else store.lkg_id()
        if target is None or store.content(target) is None:
            return {"ok": False, "reason": "no version to roll back to"}
        store.set_active(target)
        self.audit.record("rollback", name, restored=target, author=author)
        return {"ok": True, "active": target}

    # ── introspection ───────────────────────────────────────────────
    def list_skills(self) -> list[dict]:
        out = []
        for name in _EXT:
            store = self._store(name)
            out.append(
                {
                    "name": name,
                    "active": store.active_id(),
                    "last_known_good": store.lkg_id(),
                    "staged": store.staged_id(),
                    "boot_attempt": store.boot_attempt_id(),
                    "versions": len(store.history()),
                }
            )
        return out

    def history(self, name: str) -> list[dict]:
        return self._store(name).history()
