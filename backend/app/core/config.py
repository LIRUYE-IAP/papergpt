from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "PaperGPT API"
    api_v1_prefix: str = "/api/v1"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    storage_root: Path = PROJECT_ROOT / "storage"
    jwt_expiration_minutes: int = Field(default=60, gt=0)
    max_pdf_upload_mb: int = Field(default=20, gt=0, le=1024)
    frontend_origin: str = "http://localhost:3000"

    ai_provider: str = "mock"
    openai_api_key: str | None = None
    openai_translation_model: str = "gpt-5-mini"
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("storage_root", mode="after")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
