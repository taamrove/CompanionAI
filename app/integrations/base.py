"""Connector base class.

A connector pulls data from an external service and turns it into memories
the companion can recall. OpenHuman auto-syncs ~118 services every 20 min;
this is the same idea, kept minimal and self-hostable.
"""

from __future__ import annotations

from app.memory.store import MemoryStore


class Connector:
    #: Stable identifier, e.g. "gmail".
    name: str = "base"

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def configured(self) -> bool:
        """Whether this connector has the credentials it needs to sync."""
        return False

    async def sync(self, session_id: str) -> int:
        """Pull fresh data and write memories. Returns the number written."""
        raise NotImplementedError
