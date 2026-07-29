import pytest
from pydantic import ValidationError

from app.globals import Environment, Settings


def test_default_environment_is_local(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    settings = Settings(_env_file=None)
    assert settings.env is Environment.LOCAL
    assert settings.is_local is True


@pytest.mark.parametrize("env_value", ["local", "stg", "prod"])
def test_accepts_valid_environments(env_value):
    settings = Settings(_env_file=None, env=env_value)
    assert settings.env.value == env_value


def test_rejects_invalid_environment():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env="production")


def test_database_url_uses_settings_fields():
    settings = Settings(
        _env_file=None,
        db_user="app",
        db_password="secret",
        db_host="db",
        db_port=3306,
        db_name="apron",
    )
    assert settings.database_url == "mysql+pymysql://app:secret@db:3306/apron"
