# CompanionAI — Safety Architecture

This document is the source of truth for **what the AI may change about itself,
and what guarantees keep that safe.** It is human-owned and lives in the trusted
root.

## The principle

A self-modifying system can roll back a change to anything **except the
mechanism that performs the rollback.** So there is always an irreducible
**trusted root** that stays human-controlled. Everything else can self-improve,
as long as it does so *on top of* that root, reversibly, under supervision.

## Three layers

```
╔═ TRUSTED ROOT — immutable to the AI, human-only via git + deploy ═══════╗
║  • supervisor:  watchdog · rollback · known-good store · kill switch     ║
║  • security:    auth · secrets · memory integrity                       ║
║  • module host: loader · sandbox · permission-gated host API            ║
╠═ MUTABLE CORE — self-editable application logic, staged + rolled back ══╣
║  • router/routing · retrieval · orchestration · formatting              ║
╠═ MODULES & SKILLS — userland that runs on top of the core ═════════════╣
║  • modules/ (plug-ins, Bitfocus-style) · skills/ (persona, routing)     ║
╚═════════════════════════════════════════════════════════════════════════╝
```

The partition is encoded in [`core/trusted/manifest.py`](core/trusted/manifest.py)
(`TRUSTED` / `MUTABLE`) and enforced by `is_mutable()` — **fail-closed**: anything
not explicitly mutable, or overlapping the trusted root, cannot be changed by the
AI.

## How a self-improvement lands (stage → apply on restart → confirm/rollback)

1. **Stage.** The AI submits a new skill version (or, later, a new module
   version). It is snapshotted and health-checked but the **live system is not
   touched**.
2. **Trigger.** The **watchdog** (separate container) sees the staged change and
   restarts the brain to apply it.
3. **Boot + health gate.** The kernel promotes the staged version and
   health-checks it. `last_known_good` deliberately lags by one boot.
4. **Probation.** The watchdog watches `/health`:
   - healthy throughout → `POST /selfimprove/confirm` → promoted to known-good;
   - crash / unhealthy → restart → the boot **crash-sentinel auto-rolls-back** to
     the last-known-good version.

## Guarantees (all covered by tests)

- **Master kill switch** (`SELFIMPROVE_ENABLED`) lives in the kernel; the AI
  cannot enable its own ability to self-modify.
- **Health gate** rejects broken/unsafe revisions before they apply.
- **Auto-rollback** on a failed boot or crash loop; known-good is never the
  version that just broke.
- **Always functions** — runtime fallback chain active → good → shipped →
  baked-in default.
- **External supervision** — the watchdog is outside the brain; the component
  being improved never confirms its own success.
- **Trust partition is enforced**, not documented — `is_mutable()` gates every
  change; modules get only the permissions they declared.
- **Fully audited & reversible** — `audit.jsonl`; every version kept.

## The sharp edge (read before widening scope)

Crash-rollback catches changes that **crash**. It does **not** catch a change
that boots green but is **silently harmful** — e.g. one that quietly weakens
auth. That is exactly why **security stays in the trusted root**. If mutable
core or modules are ever allowed to touch security-sensitive behaviour, the
probation gate must become a real **security/regression test suite** the
supervisor runs before confirming — not just "is the process up?".

## Modules (userland on top of the core)

Modules are plug-ins (à la Bitfocus Companion) that extend the companion without
touching the core. A module talks only to a **permission-gated host API**
(`core/trusted/modules/host.py`) — never the DB, settings, secrets, or auth. A
module that errors on load is isolated out; the core keeps running. See
[`modules/README.md`](modules/README.md).

**Current limitation:** modules load in-process. Permission gating is enforced
now; **process isolation** (each module in its own child process, so a crash or
hang can't affect the core) is the next hardening step.

## What stays human-only, always

- The watchdog and the rollback machinery.
- Auth, secrets, and memory integrity.
- The module host and this trust partition.

Changing any of these is a normal human code change: edit, review, test, deploy.
