"""Global, project-level configuration.

Centralizes every environment-driven and sensitive value (DB credentials,
secrets, etc.) behind a single `Settings` object so the rest of the app never
reads `os.environ` directly.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STG = "stg"
    PROD = "prod"


class Settings(BaseSettings):
    """Values are read from process env vars first, then from a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Deployment environment. Must be one of Environment's values.
    env: Environment = Environment.LOCAL

    # App metadata
    app_name: str = "project-new-apron-backend"
    api_v1_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Secrets / sensitive config
    secret_key: SecretStr = Field(default=SecretStr("insecure-dev-secret-change-me"))

    # Database
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "project_new_apron"
    db_user: str = "root"
    db_password: SecretStr = Field(default=SecretStr(""))

    # Auth / JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Login lockout: after this many consecutive failures, lock out the
    # account with exponential backoff (doubling each additional failure).
    login_lockout_threshold: int = 3
    login_lockout_base_minutes: int = 1

    # CORS: comma-separated list of allowed origins (web frontend, etc.)
    cors_origins: str = "http://localhost:3000"

    # Recipe photo uploads: local disk storage, served back under media_url_prefix.
    upload_dir: str = "uploads"
    media_url_prefix: str = "/media"
    max_image_size_bytes: int = 2 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_local(self) -> bool:
        return self.env is Environment.LOCAL

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
