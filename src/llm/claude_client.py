from __future__ import annotations

from anthropic import Anthropic

from src.config import settings


def get_client() -> Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=settings.anthropic_api_key)


def model_name() -> str:
    return settings.anthropic_model
