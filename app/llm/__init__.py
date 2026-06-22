"""Hybrid LLM layer: local Ollama + cloud Claude, with routing."""

from app.llm.router import LLMRouter

__all__ = ["LLMRouter"]
