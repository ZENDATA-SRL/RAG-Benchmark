from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# Settings read from `.env` before the process environment. Langfuse keys are often
# exported in a shell profile for some other project, and traces sent with those keys
# would silently land in that project.
_DOTENV_FIRST_PREFIX = "langfuse_"


class _DotenvFirst(PydanticBaseSettingsSource):
    """The `.env` values of the settings that must not be overridden by the shell."""

    def __init__(
        self, settings_cls: type[BaseSettings], dotenv: PydanticBaseSettingsSource
    ) -> None:
        super().__init__(settings_cls)
        self.dotenv = dotenv

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.dotenv().items()
            if key.startswith(_DOTENV_FIRST_PREFIX)
        }


class Settings(BaseSettings):
    """Application configuration read from environment variables / `.env`.

    Credentials live here and never in the database: the storage keys and the
    connection strings are read from the environment at startup. The process
    environment wins over `.env`, except for the Langfuse settings, where `.env` wins.
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

    chroma_host: str = "localhost"
    chroma_port: int = 8001

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    max_upload_bytes: int = 200 * 1024 * 1024
    allowed_mime_types: tuple[str, ...] = ("application/pdf",)

    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
    )
    log_level: str = "INFO"

    # Tracing of Q&A executions. Off unless both keys are set: the platform never depends
    # on Langfuse being there.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str | None = None
    langfuse_timeout_s: int = 10

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _DotenvFirst(settings_cls, dotenv_settings),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @property
    def langfuse_enabled(self) -> bool:
        """Whether executions are traced: both Langfuse keys are configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
