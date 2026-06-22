"""Embed-and-recall over the memory store.

Cosine similarity in pure Python — fine for a personal-scale vault. If
embeddings are unavailable (Ollama down / no embed model), falls back to a
keyword overlap score so recall still works, just less precisely.
"""

from __future__ import annotations

import math

from core.llm.router import LLMRouter
from core.memory.store import MemoryStore


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_overlap(query: str, text: str) -> float:
    q = set(query.lower().split())
    t = set(text.lower().split())
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


class Retriever:
    def __init__(self, store: MemoryStore, router: LLMRouter) -> None:
        self.store = store
        self.router = router

    async def search(
        self, query: str, session_id: str | None = None, top_k: int = 5
    ) -> list[dict]:
        memories = self.store.all_memories(session_id)
        if not memories:
            return []

        query_vec = await self.router.embed(query)
        scored = []
        for m in memories:
            if query_vec and m.get("embedding"):
                score = _cosine(query_vec, m["embedding"])
            else:
                score = _keyword_overlap(query, m["text"])
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"text": m["text"], "kind": m["kind"], "score": round(score, 4)}
            for score, m in scored[:top_k]
            if score > 0
        ]
