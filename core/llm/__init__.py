"""Hybrid LLM layer: local Ollama + cloud Claude, with routing."""

from core.llm.router import LLMRouter

__all__ = ["LLMRouter"]
