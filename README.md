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

## Repository layout

```
app/
  main.py              FastAPI app + router wiring
  config.py            env-driven settings
  llm/                 hybrid LLM routing (cloud Claude + local Ollama)
  memory/              SQLite store + Markdown vault
  rag/                 embeddings + retrieval
  voice/               STT / TTS endpoints (pluggable backends)
  integrations/        connector framework + Gmail stub
  api/                 HTTP route handlers
web/                   minimal chat + vault web UI
data/                  SQLite db + vault (created at runtime; gitignored)
```

## Roadmap

1. ✅ Chat + persistent memory + RAG + hybrid routing (this scaffold)
2. Voice: ship a default local STT (faster-whisper) + TTS (Piper) backend
3. Integrations: finish Gmail OAuth + auto-sync loop; add more connectors
4. A richer vault browser UI; lip-synced mascot
