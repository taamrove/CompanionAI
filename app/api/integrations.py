"""Integration (connector) routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("")
async def list_integrations(request: Request) -> dict:
    connectors = request.app.state.connectors
    out = []
    for name, conn in connectors.items():
        out.append({"name": name, "configured": await conn.configured()})
    return {"connectors": out}


@router.post("/{name}/sync")
async def sync_integration(
    name: str, request: Request, session_id: str = "default"
) -> dict:
    connectors = request.app.state.connectors
    conn = connectors.get(name)
    if conn is None:
        raise HTTPException(status_code=404, detail=f"No connector named '{name}'.")
    try:
        written = await conn.sync(session_id)
    except (RuntimeError, NotImplementedError) as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"connector": name, "memories_written": written}
