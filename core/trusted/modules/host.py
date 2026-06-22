"""Module host: discovery, sandboxed load, and a permission-gated host API.

Contract (a module is a directory under ``modules/<id>/``):
  * ``module.json`` — manifest: id, name, version, entrypoint, permissions, …
  * the entrypoint file exposes ``setup(host: HostAPI) -> None`` (or a ``Module``
    subclass whose ``setup`` is called).

A module declares the permissions it needs; the host wires ONLY those
capabilities into its HostAPI. Anything it didn't declare raises PermissionError.
Security-critical capabilities (secrets, auth, raw memory) are never exposed —
they stay in the trusted core, reachable only through gated host calls.

NOTE: modules currently load in-process. The permission boundary is enforced
now; full process isolation (à la Bitfocus running each module in its own
child process) is the next hardening step — see SAFETY.md.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from typing import Awaitable, Callable

# Capabilities a module may request. Deliberately small and security-aware.
KNOWN_PERMISSIONS = {"memory:read", "memory:write", "tools:register", "log"}


class HostAPI:
    """The only surface a module can touch. Scoped to its granted permissions."""

    def __init__(self, host: "ModuleHost", module_id: str, perms: set[str]) -> None:
        self._host = host
        self._id = module_id
        self._perms = perms

    def _require(self, perm: str) -> None:
        if perm not in self._perms:
            raise PermissionError(
                f"module '{self._id}' lacks permission '{perm}'"
            )

    def log(self, msg: str) -> None:
        self._require("log")
        print(f"[module:{self._id}] {msg}", flush=True)

    async def remember(self, text: str, kind: str = "fact") -> None:
        self._require("memory:write")
        await self._host._remember(text, kind)

    async def search_memory(self, query: str, top_k: int = 5) -> list[dict]:
        self._require("memory:read")
        return await self._host._search(query, top_k)

    def register_tool(self, definition: dict, handler: Callable) -> None:
        self._require("tools:register")
        self._host._register_tool(self._id, definition, handler)


class Module:
    """Optional base class. Modules may instead expose a ``setup(host)`` function."""

    def setup(self, host: HostAPI) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ModuleHost:
    def __init__(
        self,
        modules_dir: Path,
        *,
        remember: Callable[[str, str], Awaitable[None]],
        search: Callable[[str, int], Awaitable[list[dict]]],
        audit=None,
        allowed_permissions: set[str] | None = None,
    ) -> None:
        self.dir = Path(modules_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._remember = remember
        self._search = search
        self._audit = audit
        self._allowed = allowed_permissions or set(KNOWN_PERMISSIONS)
        self.modules: dict[str, dict] = {}            # id -> {manifest, enabled, error}
        self._tools: dict[str, tuple[Callable, str]] = {}  # name -> (handler, module_id)
        self._tool_defs: list[dict] = []

    def _log(self, action: str, module: str, **fields) -> None:
        if self._audit is not None:
            self._audit.record(action, module, **fields)

    # ── discovery + sandboxed load ──────────────────────────────────
    def discover_and_load(self) -> None:
        for entry in sorted(self.dir.iterdir()) if self.dir.exists() else []:
            manifest = entry / "module.json"
            if entry.is_dir() and manifest.is_file():
                self.load_module(entry)

    def load_module(self, path: Path) -> None:
        try:
            manifest = json.loads((path / "module.json").read_text(encoding="utf-8"))
            mid = manifest["id"]
        except Exception as exc:
            self._log("module_invalid", path.name, detail=str(exc))
            return

        perms = set(manifest.get("permissions", []))
        unknown = perms - KNOWN_PERMISSIONS
        denied = perms - self._allowed
        if unknown or denied:
            self.modules[mid] = {"manifest": manifest, "enabled": False,
                                 "error": f"permissions not granted: {unknown | denied}"}
            self._log("module_denied", mid, permissions=sorted(perms))
            return

        try:
            entrypoint = path / manifest.get("entrypoint", "module.py")
            spec = importlib.util.spec_from_file_location(
                f"companion_module_{mid}_{uuid.uuid4().hex[:8]}", entrypoint
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            api = HostAPI(self, mid, perms)
            if hasattr(mod, "setup"):
                mod.setup(api)
            elif hasattr(mod, "Module"):
                mod.Module().setup(api)
            else:
                raise RuntimeError("module exposes neither setup() nor Module")

            self.modules[mid] = {"manifest": manifest, "enabled": True, "error": None}
            self._log("module_loaded", mid, version=manifest.get("version"))
        except Exception as exc:
            # Isolate the bad module out — the core keeps running.
            self.modules[mid] = {"manifest": manifest, "enabled": False, "error": str(exc)}
            self._log("module_disabled", mid, detail=str(exc))

    # ── tools contributed by modules ────────────────────────────────
    def _register_tool(self, module_id: str, definition: dict, handler: Callable) -> None:
        name = definition["name"]
        self._tools[name] = (handler, module_id)
        self._tool_defs.append(definition)

    def tools(self) -> list[dict]:
        return list(self._tool_defs)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def dispatch(self, name: str, tool_input: dict):
        handler, _ = self._tools[name]
        result = handler(tool_input)
        if hasattr(result, "__await__"):
            result = await result
        return result

    def list_modules(self) -> list[dict]:
        return [
            {
                "id": mid,
                "name": info["manifest"].get("name", mid),
                "version": info["manifest"].get("version"),
                "permissions": info["manifest"].get("permissions", []),
                "enabled": info["enabled"],
                "error": info["error"],
            }
            for mid, info in self.modules.items()
        ]
