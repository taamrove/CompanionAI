"""Routes each request to local (Ollama) or cloud (Claude).

Policy (mode = ``hybrid``):
  * Light, conversational turns  → local Ollama  (fast, free, offline)
  * Heavy lifting                → cloud Claude  (deep reasoning, tools)

"Heavy" is decided by a cheap heuristic (length + intent keywords). It is
deliberately simple and easy to tune; swap in a classifier later if you want.
"""

from __future__ import annotations

from app.config import Settings
from app.llm.cloud import CloudClient
from app.llm.local import OllamaClient

# Words that signal the user wants real reasoning / tools, not chit-chat.
_HEAVY_HINTS = (
    "analyze", "analyse", "research", "plan", "code", "debug", "write",
    "summarize", "summarise", "compare", "explain", "design", "draft",
    "calculate", "review", "translate", "step by step", "why", "how do",
)


class LLMRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.local = OllamaClient(
            settings.ollama_base_url, settings.local_model, settings.embed_model
        )
        self.cloud: CloudClient | None = (
            CloudClient(settings.anthropic_api_key, settings.cloud_model, settings.cloud_effort)
            if settings.cloud_available
            else None
        )

    def use_cloud(self, message: str) -> bool:
        """Decide whether this turn should go to the cloud brain."""
        mode = self.settings.llm_mode
        if mode == "local_only":
            return False
        if mode == "cloud_only":
            return self.cloud is not None
        # hybrid
        if self.cloud is None:
            return False
        lowered = message.lower()
        if len(message) > 280:
            return True
        return any(hint in lowered for hint in _HEAVY_HINTS)

    async def embed(self, text: str) -> list[float] | None:
        """Embeddings always come from the local model (keeps vectors local
        and consistent). Returns None if Ollama/embeddings are unavailable."""
        try:
            return await self.local.embed(text)
        except Exception:
            return None

    async def status(self) -> dict:
        return {
            "mode": self.settings.llm_mode,
            "local": {
                "model": self.settings.local_model,
                "reachable": await self.local.healthy(),
            },
            "cloud": {
                "model": self.settings.cloud_model if self.cloud else None,
                "configured": self.cloud is not None,
            },
        }
