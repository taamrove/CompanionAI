"""The module host (trusted root).

Loads plug-in modules that run *on top of* the core — Bitfocus-Companion style.
The host is the security boundary: a module never receives the store, settings,
secrets, or auth. It receives a ``HostAPI`` facade scoped to the permissions its
manifest declared, and nothing else. A module that errors on load is isolated
out (disabled), never taking the core down with it.
"""

from core.trusted.modules.host import HostAPI, Module, ModuleHost

__all__ = ["HostAPI", "Module", "ModuleHost"]
