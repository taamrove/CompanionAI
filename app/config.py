"""Environment-driven settings for the CompanionAI brain."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Inference routing: hybrid | local_only | cloud_only
    llm_mode: str = "hybrid"

    # Cloud (Claude) — the heavy-lifting brain
    anthropic_api_key: str = ""
    cloud_model: str = "claude-opus-4-8"
    cloud_effort: str = "high"

    # Local (Ollama) — light, fast, offline dialogue
    ollama_base_url: str = "http://ollama:11434"
    local_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"

    # Memory / storage
    data_dir: str = "/data"
    rag_top_k: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vault_path(self) -> Path:
        p = self.data_path / "vault"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return self.data_path / "companion.db"

    @property
    def cloud_available(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
