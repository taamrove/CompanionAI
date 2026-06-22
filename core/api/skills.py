"""Self-improvement API — inspect, revise, approve, and roll back skills.

These routes are the human's control surface over the mutable layer. The master
kill switch (``SELFIMPROVE_ENABLED``) is intentionally NOT togglable here — it
lives in the kernel config so the running system can't enable its own ability
to self-modify.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["self-improvement"])


class ReviseRequest(BaseModel):
    content: str
    reason: str = ""


class RollbackRequest(BaseModel):
    to: int | None = None


@router.get("/selfimprove/status")
async def status(request: Request) -> dict:
    reg = request.app.state.companion.registry
    return {"enabled": reg.enabled, "mode": reg.mode, "skills": reg.list_skills()}


@router.get("/selfimprove/audit")
async def audit(request: Request, limit: int = 100) -> dict:
    reg = request.app.state.companion.registry
    return {"entries": reg.audit.tail(limit=limit)}


@router.post("/selfimprove/confirm")
async def confirm(request: Request) -> dict:
    """Promote the just-applied version to last-known-good. Called by the
    watchdog once the brain has stayed healthy through its probation window."""
    reg = request.app.state.companion.registry
    reg.confirm_boot()
    return {"ok": True, "skills": reg.list_skills()}


@router.get("/skills/{name}/history")
async def history(name: str, request: Request) -> dict:
    reg = request.app.state.companion.registry
    return {"skill": name, "versions": reg.history(name)}


@router.post("/skills/{name}/revise")
async def revise(name: str, req: ReviseRequest, request: Request) -> dict:
    """Human-authored revision. Same guarded path as the AI: health gate +
    auto-rollback (auto mode) or queued for approval (propose mode)."""
    reg = request.app.state.companion.registry
    if not reg.enabled:
        raise HTTPException(status_code=403, detail="Self-improvement is disabled.")
    return reg.apply(name, req.content, author="human", reason=req.reason)


@router.post("/skills/{name}/promote/{vid}")
async def promote(name: str, vid: int, request: Request) -> dict:
    reg = request.app.state.companion.registry
    if not reg.enabled:
        raise HTTPException(status_code=403, detail="Self-improvement is disabled.")
    return reg.promote(name, vid, author="human")


@router.post("/skills/{name}/rollback")
async def rollback(name: str, req: RollbackRequest, request: Request) -> dict:
    reg = request.app.state.companion.registry
    return reg.rollback(name, author="human", to=req.to)
