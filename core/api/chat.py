"""Chat + memory routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> dict:
    """Single-shot chat. Returns the final reply (cloud for heavy turns)."""
    companion = request.app.state.companion
    return await companion.chat(req.session_id, req.message)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """Two-phase chat over Server-Sent Events: an instant local 'warm' reply
    keeps the dialogue alive, then the cloud brain's final reply arrives."""
    companion = request.app.state.companion

    async def event_source():
        async for event in companion.chat_stream(req.session_id, req.message):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.get("/memory/list")
async def memory_list(request: Request, limit: int = 100) -> dict:
    companion = request.app.state.companion
    return {"notes": companion.store.vault.list_notes(limit=limit)}


@router.get("/memory/search")
async def memory_search(
    request: Request, q: str, session_id: str | None = None, top_k: int = 5
) -> dict:
    companion = request.app.state.companion
    results = await companion.retriever.search(q, session_id=session_id, top_k=top_k)
    return {"results": results}
