"""Routes each request to local (Ollama) or cloud (Claude).

Policy (mode = ``hybrid``):
  * Light, conversational turns  → local Ollama  (fast, free, offline)
  * Heavy lifting                → cloud Claude  (deep reasoning, tools)

"Heavy" is decided by a cheap heuristic (length + intent keywords) loaded from
the *routing* skill — so the companion can tune its own routing under the
self-improvement guardrails. Falls back to safe defaults if the skill is bad.
"""

from __future__ import annotations

import json

from core.config import Settings
from core.llm import cloudconfig
from core.llm.cloud import build_cloud
from core.llm.local import OllamaClient
from core.selfimprove import SkillRegistry

# Safe defaults used if the routing skill is missing or malformed.
_DEFAULT_THRESHOLD = 280
_DEFAULT_HINTS = (
    "analyze", "analyse", "research", "plan", "code", "debug", "write",
    "summarize", "summarise", "compare", "explain", "design", "draft",
    "calculate", "review", "translate", "step by step", "why", "how do",
)


class LLMRouter:
    def __init__(self, settings: Settings, registry: SkillRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.local = OllamaClient(
            settings.ollama_base_url, settings.local_model, settings.embed_model
        )
        # The cloud backend is provider-configurable at runtime (see UI/settings).
        self._cloud_cfg = cloudconfig.load(settings)
        self.cloud = build_cloud(self._cloud_cfg)

    def reload_cloud(self) -> dict:
        """Rebuild the cloud client from the persisted config (after a UI change)."""
        self._cloud_cfg = cloudconfig.load(self.settings)
        self.cloud = build_cloud(self._cloud_cfg)
        return cloudconfig.public(self._cloud_cfg)

    def cloud_config_public(self) -> dict:
        return cloudconfig.public(self._cloud_cfg)

    def update_cloud(self, patch: dict) -> dict:
        """Merge a patch into the cloud config, persist, and reload live. An
        empty/missing api_key keeps the existing one."""
        cfg = cloudconfig.load(self.settings)
        for key in ("provider", "model", "base_url", "effort"):
            if patch.get(key) is not None:
                cfg[key] = patch[key]
        if patch.get("api_key"):  # only overwrite when a new key is supplied
            cfg["api_key"] = patch["api_key"]
        cloudconfig.save(self.settings, cfg)
        return self.reload_cloud()

    def _routing_config(self) -> tuple[int, tuple[str, ...]]:
        """Load the routing heuristic from the (mutable) routing skill, with a
        hard fallback so a broken skill can never break routing."""
        try:
            data = json.loads(self.registry.load("routing"))
            threshold = int(data["length_threshold"])
            hints = tuple(str(h).lower() for h in data["heavy_hints"])
            return threshold, hints
        except Exception:
            return _DEFAULT_THRESHOLD, _DEFAULT_HINTS

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
        threshold, hints = self._routing_config()
        lowered = message.lower()
        if len(message) > threshold:
            return True
        return any(hint in lowered for hint in hints)

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
                "provider": self._cloud_cfg.get("provider") if self.cloud else None,
                "model": self._cloud_cfg.get("model") if self.cloud else None,
                "configured": self.cloud is not None,
            },
        }
