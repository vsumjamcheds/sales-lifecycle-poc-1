from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", encoding="utf-8")


def _env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


class Settings:
    """App settings from environment / project-root .env (no pydantic-settings required)."""

    @property
    def anthropic_api_key(self) -> str:
        return _env_str("ANTHROPIC_API_KEY", "")

    @property
    def anthropic_model(self) -> str:
        return _env_str("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    @property
    def database_url(self) -> str:
        return _env_str("DATABASE_URL", "sqlite:///./data/app.db")

    @property
    def chroma_path(self) -> str:
        return _env_str("CHROMA_PATH", "./data/chroma")

    @property
    def compliance_similarity_threshold(self) -> float:
        return _env_float("COMPLIANCE_SIMILARITY_THRESHOLD", 0.90)

    @property
    def api_base_url(self) -> str:
        return _env_str("API_BASE_URL", "http://127.0.0.1:8000")

    @property
    def project_root(self) -> Path:
        return _ROOT


settings = Settings()
