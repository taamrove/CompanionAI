"""Cloud inference backends — provider-configurable.

The cloud "heavy lifting" brain can be any of:
  * Anthropic (Claude) — full tool-use loop, via the official SDK.
  * Any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Together, a local
    gateway, …) — plain chat completion, via base_url + key + model.

Which one is live is chosen at runtime from the UI (see core/api/settings.py),
so you can point the companion at whatever cloud LLM you want without a redeploy.
"""

from __future__ import annotations

import httpx
from anthropic import AsyncAnthropic


class AnthropicCloud:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str = "high") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    async def create(
        self, system: str, messages: list[dict], tools: list[dict] | None = None,
        max_tokens: int = 16000,
    ):
        """One Messages API turn — returns the raw response so the caller can run
        the tool-use loop."""
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }
        if tools:
            kwargs["tools"] = tools
        return await self._client.messages.create(**kwargs)


class OpenAICompatCloud:
    provider = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, effort: str = "high") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.effort = effort

    async def complete(self, system: str, messages: list[dict], max_tokens: int = 2048) -> str:
        """Plain chat completion. Tools aren't wired for this path yet, so the
        companion's tool-calling features run best on the Anthropic backend."""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


def build_cloud(cfg: dict):
    """Construct the active cloud client from a config dict, or None if it isn't
    fully configured (no key/model)."""
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model") or ""
    if not api_key or not model:
        return None
    effort = cfg.get("effort", "high")
    if cfg.get("provider") == "openai":
        return OpenAICompatCloud(api_key, model, cfg.get("base_url", ""), effort)
    return AnthropicCloud(api_key, model, effort)
