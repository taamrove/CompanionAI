"""The trust partition — the single source of truth for what the AI may change.

Decision (locked): the immutable trusted root is the supervisor PLUS security.
Everything else in core is self-editable with watchdog rollback.

Any self-improvement action MUST pass through ``is_mutable()`` before it can
touch a path. Trusted always wins over mutable, so a path that matches both is
treated as trusted (fail-closed).
"""

from __future__ import annotations

# ── Immutable: the supervisor + security. Human-only, via git + deploy. ──
TRUSTED: tuple[str, ...] = (
    # the partition + guard themselves
    "core/trusted/",
    # the rollback machinery (registry, versioning, health gate, audit)
    "core/selfimprove/",
    # the external supervisor
    "watchdog/",
    # secrets + auth configuration
    "core/config.py",
    # auth middleware + boot sequence wiring
    "core/main.py",
    # memory integrity (the write/storage path)
    "core/memory/",
    # the module host (loader, sandbox, permission-gated host API)
    "core/trusted/modules/",
)

# ── Mutable: self-editable behaviour, protected by staged apply + rollback. ──
MUTABLE: tuple[str, ...] = (
    # userland skills (persona, routing, …)
    "skills/",
    # plug-in modules that run on top of the core (Bitfocus-Companion style)
    "modules/",
    # application logic the AI may improve
    "core/llm/router.py",
    "core/llm/cloud.py",
    "core/llm/local.py",
    "core/rag/",
    "core/service.py",
    "core/voice/",
    "core/integrations/",
    "core/api/chat.py",
    "core/api/integrations.py",
)


def _norm(path: str) -> str:
    return path.strip().lstrip("./").strip("/").replace("\\", "/")


def _under(path: str, roots: tuple[str, ...]) -> bool:
    p = _norm(path)
    for r in roots:
        r = r.strip("/")
        if p == r or p.startswith(r + "/"):
            return True
    return False


def is_trusted(path: str) -> bool:
    """True if the path is part of the immutable trusted root."""
    return _under(path, TRUSTED)


def is_mutable(path: str) -> bool:
    """True only if the path is explicitly mutable AND not trusted.

    Fail-closed: anything not listed as mutable, or that overlaps the trusted
    root, is NOT mutable.
    """
    if is_trusted(path):
        return False
    return _under(path, MUTABLE)
