"""CompanionAI brain — FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat as chat_routes
from app.api import integrations as integration_routes
from app.config import get_settings
from app.integrations.gmail import GmailConnector
from app.service import Companion
from app.voice.routes import router as voice_router

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
