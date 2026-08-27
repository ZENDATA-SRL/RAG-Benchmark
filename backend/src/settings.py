from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration read from environment variables / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RAG Benchmark API"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/rag-bench"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
