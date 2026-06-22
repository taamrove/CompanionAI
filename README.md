# CompanionAI

A local-first, self-hostable AI companion — our own take on
[`tinyhumansai/openhuman`](https://github.com/tinyhumansai/openhuman).

The whole thing runs as a Docker container on your own server. It is the
**brain**: a single HTTP API that any client (the bundled web UI, a phone app,
a CLI, a voice device) can talk to.

## What it does

| Pillar | Status | Notes |
|---|---|---|
| 💬 **Chat + persistent memory** | ✅ working | Talk to the companion; it remembers across sessions in SQLite + a browsable Markdown vault |
| 🧠 **RAG / vault retrieval** | ✅ working | Past memories & notes are embedded and recalled automatically |
| 🔀 **Hybrid inference** | ✅ working | Light dialogue on local **Ollama**, heavy lifting on cloud **Claude** — routed automatically |
| 🎙️ **Voice (STT/TTS)** | 🟡 wired, pluggable | Endpoints + pluggable backends (faster-whisper / Piper / ElevenLabs) |
| 🔌 **Integrations (Gmail, …)** | 🟡 skeleton | Connector framework + a Gmail connector stub that feeds memory |

## Architecture

```
┌──────────────────────────────────────────────┐
│  Clients: bundled web UI · phone · CLI · voice │
└───────────────────────┬──────────────────────┘
                        │ HTTP / JSON
┌───────────────────────┴──────────────────────┐
│  CompanionAI brain (this container)           │
│   • /chat        chat loop + tool calling      │
│   • /voice/*     STT / TTS                      │
│   • /memory/*    vault browse / search          │
│   • /integrations/*  connectors → memory        │
│                                                │
│   LLM router ── local (Ollama)  ◄─ light        │
│             └── cloud (Claude)  ◄─ heavy        │
│   Memory ── SQLite (facts + embeddings)         │
│          └── Markdown vault (Obsidian-style)    │
└───────────┬──────────────────────┬────────────┘
            │                      │
      Ollama (local)         Anthropic API (cloud)
```

## Quick start

```bash
cp .env.example .env
# edit .env — at minimum set ANTHROPIC_API_KEY if you want cloud "heavy lifting"

docker compose up --build
```

Then open <http://localhost:8080> for the chat UI, or hit the API directly:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/chat -H 'content-type: application/json' \
  -d '{"session_id":"me","message":"Remember that my dog is named Biscuit."}'
```

`docker compose` also starts an **Ollama** service for fully-local dialogue.
Pull a model into it once it's up:

```bash
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text   # for embeddings/RAG
```

## Configuration

Everything is environment-driven — see [`.env.example`](.env.example).
Key knobs:

- `LLM_MODE` — `hybrid` (default), `local_only`, or `cloud_only`
- `CLOUD_MODEL` — Claude model for heavy lifting (default `claude-opus-4-8`)
- `LOCAL_MODEL` — Ollama model for light dialogue (default `llama3.2`)
- `OLLAMA_BASE_URL`, `ANTHROPIC_API_KEY`

## iPhone

The brain is a plain HTTP API, so the phone is just another client. Three tiers,
cheapest first:

1. **Install the Archive as an app (PWA) — works today.** Open the server URL in
   Safari → Share → *Add to Home Screen*. The bundled `manifest.webmanifest` +
   service worker make it launch full-screen with its own icon. The 3D Archive
   runs on iOS WebGL.
2. **Siri Shortcuts / Action Button — voice, hands-free.** A "Get Contents of
   URL" shortcut that POSTs to `/chat` lets you say *"Hey Siri, ask Companion…"*,
   speak your message, and have iOS read the reply aloud — no App Store needed.
3. **Native SwiftUI app — the ceiling.** Native Speech + AVSpeech voice, push
   notifications for a *proactive* companion, Home-Screen widgets / Live
   Activities, and the Archive rendered in SceneKit/RealityKit. Talks to the
   same API.

**Reaching your server safely:** put the brain and your phone on a private
[Tailscale](https://tailscale.com) network (recommended — no public exposure),
or expose it behind a reverse proxy and set `API_TOKEN`. Clients then send
`Authorization: Bearer <token>`; the web UI picks it up from `?token=…` once.

## Self-improving core (safe by construction)

The companion can improve its own behaviour — but only the parts that can't hurt
it, and never without a safety net. The design is a two-ring kernel/userland
split plus an external watchdog.

```
┌─ core/  (kernel — immutable to the AI) ────────────────┐
│  router · memory · auth · the skill registry           │
│  health gate · versioning · rollback · audit · switch  │
├─ skills/  (userland — the AI may revise) ──────────────┤
│  persona (system prompt) · routing heuristics · …      │
└────────────────────────────────────────────────────────┘
        ▲ stages changes              ▲ triggers + confirms/rolls back
        │                             │
   the AI (gated by master switch)    watchdog  (separate container)
```

**How a self-improvement actually lands — stage, then apply on restart:**

1. The AI (or a human) submits a new skill version. It is **staged**, not live —
   the running companion is untouched.
2. The **watchdog** (a separate container) sees the staged change and **triggers
   the apply by restarting the brain**.
3. On boot the kernel promotes the staged version and **health-checks** it.
   `last_known_good` deliberately lags one step.
4. The watchdog watches health through a **probation window**:
   - healthy throughout → `POST /selfimprove/confirm` → promoted to good;
   - crash / unhealthy → restart → the boot **crash-sentinel auto-rolls-back** to
     the last-known-good version.

**The guarantees (all covered by the test suite):**

- **Master kill switch** (`SELFIMPROVE_ENABLED`) lives in the kernel — the AI
  cannot enable its own ability to self-modify.
- **Health gate** rejects broken/unsafe revisions before they apply.
- **Auto-rollback** on a failed boot or a crash loop; `last_known_good` is never
  the version that just broke.
- **Always functions** — a missing/corrupt skill falls back active → good →
  shipped → baked-in default at runtime.
- **External supervision** — the watchdog is outside the brain, so it survives
  crashes and forces recovery; the thing being improved never declares its own
  change a success.
- **Fully audited & reversible** — every action is in `audit.jsonl`; every
  version is kept; one call rolls back.

Run with supervision: set `SELFIMPROVE_ENABLED=true` and `SELF_CONFIRM_SECONDS=0`
in `.env`, then `docker compose --profile watchdog up --build`.

The trusted root (supervisor + security + module host) is encoded in
[`core/trusted/manifest.py`](core/trusted/manifest.py) and enforced fail-closed.
Full rationale and invariants: **[SAFETY.md](SAFETY.md)**.

### Modules (plug-ins on top of the core)

Like [Bitfocus Companion](https://bitfocus.io/companion), behaviour is extended
with **modules** that run on top of the core through a permission-gated host API
— they never touch the DB, secrets, or auth. See [`modules/README.md`](modules/README.md);
the bundled `clock` module adds a `get_time` tool as a template.

## Repository layout

```
core/                  the KERNEL
  trusted/             TRUSTED ROOT — immutable to the AI (partition + module host)
    manifest.py        the trust partition (TRUSTED / MUTABLE) + guard
    modules/           module host: loader · sandbox · permission-gated API
  selfimprove/         skill registry · versioning · health · rollback · audit
  memory/              SQLite store + Markdown vault (integrity = trusted)
  config.py            env-driven settings (secrets/auth = trusted)
  main.py              FastAPI app, boot sequence, auth
  llm/                 hybrid LLM routing (mutable)
  rag/                 embeddings + retrieval (mutable)
  service.py           orchestration (mutable)
  voice/ integrations/ api/   endpoints / connectors
skills/                USERLAND — versioned behaviour the AI may revise
  persona/  routing/   system prompt + local-vs-cloud heuristic
modules/               USERLAND plug-ins on top of the core (e.g. clock/)
watchdog/              external supervisor container
web/                   3D "Archive" UI (+ classic.html fallback)
data/                  SQLite db, vault, skill versions, audit (gitignored)
```

## Roadmap

1. ✅ Chat + persistent memory + RAG + hybrid routing (this scaffold)
2. Voice: ship a default local STT (faster-whisper) + TTS (Piper) backend
3. Integrations: finish Gmail OAuth + auto-sync loop; add more connectors
4. A richer vault browser UI; lip-synced mascot
