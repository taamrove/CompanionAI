# modules/ — plug-ins that run on top of the core

Inspired by [Bitfocus Companion](https://bitfocus.io/companion)'s module system.
A module extends the companion **without touching the core**. It talks only to a
stable, permission-gated **host API** — it never sees the database, settings,
secrets, or auth.

## Anatomy

```
modules/<id>/
  module.json     manifest: id, name, version, entrypoint, permissions
  module.py       exposes setup(host) — wires the module into the host
```

`module.json`:

```json
{
  "id": "clock",
  "name": "Clock",
  "version": "0.1.0",
  "entrypoint": "module.py",
  "permissions": ["tools:register", "log"],
  "description": "Adds a get_time tool."
}
```

`module.py`:

```python
def setup(host):
    host.register_tool({...}, handler)   # needs "tools:register"
    # host.remember(text)                # needs "memory:write"
    # host.search_memory(query)          # needs "memory:read"
    # host.log("...")                    # needs "log"
```

## Permissions

A module gets **only** the capabilities it declares (and that policy allows).
Anything else raises `PermissionError`. Security-critical capabilities
(secrets, auth, raw DB access) are never exposed — they stay in the trusted
core. Current set: `memory:read`, `memory:write`, `tools:register`, `log`.

## Safety

- A module that errors on load is **isolated out** (disabled) — the core keeps
  running.
- Modules live in the **mutable** layer (see `SAFETY.md`): they are what the AI
  may add/improve, under the staged-apply + watchdog-rollback guarantees.
- Today modules load in-process; **process isolation** (each module in its own
  child process, Bitfocus-style) is the next hardening step.
