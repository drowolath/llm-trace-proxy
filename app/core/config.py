from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the proxy, sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "LLM-Trace-Proxy"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    upstream_base_url: AnyHttpUrl = Field(default=AnyHttpUrl("https://api.openai.com"))
    upstream_api_key: str | None = Field(default=None)

    connect_timeout: float = Field(default=5.0)
    read_timeout: float = Field(default=60.0)
    write_timeout: float = Field(default=10.0)
    pool_timeout: float = Field(default=5.0)

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    sentry_dsn: str | None = Field(default=None)
    betterstack_source_token: str | None = Field(default=None)


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
