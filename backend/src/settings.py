from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration read from environment variables / `.env`.

    Credentials live here and never in the database (RT-S01): the storage keys and the
    connection strings are read from the environment at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RAG Benchmark API"
    app_version: str = "0.1.0"

    database_url: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/rag-bench"
    )
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    test_database_url: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/rag-bench-test"
    )

    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "rag-bench"
    storage_region: str = "us-east-1"
    storage_secure: bool = False

    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "rag-bench"

    chroma_host: str = "localhost"
    chroma_port: int = 8001

    max_upload_bytes: int = 200 * 1024 * 1024
    allowed_mime_types: tuple[str, ...] = ("application/pdf",)

    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
    )
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
