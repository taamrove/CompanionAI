"""Runtime cloud-LLM configuration (provider, model, key, base_url).

Stored as ``<DATA_DIR>/cloud.json`` so it can be changed live from the UI and
persists across restarts. Falls back to the values in .env when unset. The API
key is a secret — it's written here (gitignored data dir) and never returned by
the API in cleartext.
"""

from __future__ import annotations

import json

from core.config import Settings

PROVIDERS = ("anthropic", "openai")


def _path(settings: Settings):
    return settings.data_path / "cloud.json"


def load(settings: Settings) -> dict:
    cfg: dict = {}
    p = _path(settings)
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg.setdefault("provider", "anthropic")
    cfg.setdefault("model", settings.cloud_model)
    cfg.setdefault("effort", settings.cloud_effort)
    cfg.setdefault("base_url", "")
    # Seed the Anthropic key from .env only for the anthropic provider.
    if cfg["provider"] == "anthropic" and not cfg.get("api_key"):
        cfg["api_key"] = settings.anthropic_api_key
    cfg.setdefault("api_key", "")
    return cfg


def save(settings: Settings, cfg: dict) -> None:
    _path(settings).write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def public(cfg: dict) -> dict:
    """Config safe to return over the API — no secret."""
    return {
        "provider": cfg.get("provider", "anthropic"),
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        "effort": cfg.get("effort", "high"),
        "has_key": bool(cfg.get("api_key")),
        "providers": list(PROVIDERS),
    }
