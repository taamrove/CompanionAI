"""Runtime settings — pick the cloud LLM provider/model/key from the UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["settings"])


class CloudPatch(BaseModel):
    provider: str | None = None      # "anthropic" | "openai"
    model: str | None = None
    api_key: str | None = None       # write-only; blank keeps the existing key
    base_url: str | None = None      # for OpenAI-compatible endpoints
    effort: str | None = None        # low | medium | high | max (anthropic)


@router.get("/settings/cloud")
async def get_cloud(request: Request) -> dict:
    return request.app.state.companion.router.cloud_config_public()


@router.put("/settings/cloud")
async def put_cloud(patch: CloudPatch, request: Request) -> dict:
    router_ = request.app.state.companion.router
    return router_.update_cloud(patch.model_dump(exclude_none=True))
