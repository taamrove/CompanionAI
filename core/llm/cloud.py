"""Cloud inference via Claude — the heavy-lifting brain.

Uses the official Anthropic SDK. Adaptive thinking is on by default for
non-trivial reasoning, and tool use is supported so the companion can search
and save its own memory.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic


class CloudClient:
    def __init__(self, api_key: str, model: str, effort: str = "high") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    async def create(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 16000,
    ):
        """One Messages API turn. Returns the raw response so the caller can
        run the tool-use loop."""
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
