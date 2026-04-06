from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    database_url: str = "sqlite:///./data/app.db"
    chroma_path: str = "./data/chroma"

    compliance_similarity_threshold: float = 0.90

    api_base_url: str = "http://127.0.0.1:8000"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent


settings = Settings()
