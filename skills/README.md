# skills/ — userland (mutable layer)

This directory holds the **shipped baselines** for the behaviours the companion
is allowed to improve: its persona, its routing heuristics, formatters, and
connectors. Think of it as "userland" — the kernel in [`core/`](../core) loads
these as *data*, never trusting them with anything safety-critical.

## How a change actually happens

The AI never edits a running file here directly. Every revision goes through the
kernel's guarded path (`core/selfimprove/`):

```
revise → snapshot new version → activate → HEALTH CHECK
                                              ├─ pass → keep, mark last-known-good
                                              └─ fail → AUTO-ROLLBACK to last-known-good
```

- Every version is stored and **reversible** (`POST /skills/{name}/rollback`).
- Every action is written to an append-only **audit log**.
- Self-improvement is **off until a human flips the master switch**
  (`SELFIMPROVE_ENABLED=true`). The AI cannot flip it — that lives in the kernel.
- If a skill file is ever missing or corrupt at runtime, the kernel falls back
  to last-known-good, then to the baked-in default, so the companion **never
  stops functioning.**

## What's here

| Skill | File | Controls |
|---|---|---|
| `persona` | `persona/active.md` | the companion's system prompt / character |
| `routing` | `routing/active.json` | when a turn goes to the cloud brain vs local |

The shipped files are the baseline (version 1). Runtime versions live under
`<DATA_DIR>/skills/` so the image stays clean and the git history stays
human-owned.
