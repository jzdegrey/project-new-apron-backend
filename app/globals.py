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
