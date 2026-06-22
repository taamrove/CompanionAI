"""CompanionAI brain — FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.api import chat as chat_routes
from core.api import integrations as integration_routes
from core.api import skills as skill_routes
from core.config import get_settings
from core.integrations.gmail import GmailConnector
from core.service import Companion
from core.voice.routes import router as voice_router

settings = get_settings()
app = FastAPI(title="CompanionAI", version="0.1.0")

# Shared, long-lived state.
companion = Companion(settings)
app.state.companion = companion
app.state.connectors = {
    "gmail": GmailConnector(companion.store),
}

app.include_router(chat_routes.router)
app.include_router(voice_router)
app.include_router(integration_routes.router)
app.include_router(skill_routes.router)


@app.on_event("startup")
async def _startup() -> None:
    # Apply any staged skill revisions (with health gate + crash rollback)…
    companion.registry.boot()
    # …then confirm the boot as healthy. When a watchdog runs it owns this call
    # (POST /selfimprove/confirm) — set SELF_CONFIRM_SECONDS=0. Standalone, the
    # brain self-confirms after a crash-free grace period. If the process dies
    # before confirmation, the next boot rolls the change back.
    grace = settings.self_confirm_seconds
    if grace > 0:
        async def _confirm_after_grace() -> None:
            await asyncio.sleep(grace)
            companion.registry.confirm_boot()

        asyncio.create_task(_confirm_after_grace())


# Protected API prefixes when API_TOKEN is set. The static UI shell stays open
# so the page can load and supply the token via ?token=… (then localStorage).
_PROTECTED = ("/chat", "/memory", "/voice", "/integrations", "/skills", "/selfimprove")


@app.middleware("http")
async def require_token(request: Request, call_next):
    if settings.api_token and request.url.path.startswith(_PROTECTED):
        header = request.headers.get("authorization", "")
        if header != f"Bearer {settings.api_token}":
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm": await companion.router.status()}


# Serve the bundled web UI at "/".
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index(_: Request) -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))
