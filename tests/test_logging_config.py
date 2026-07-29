import logging

import pytest

from app.logging_config import LOG_FORMAT


def test_log_format_includes_required_fields():
    assert "%(asctime)s" in LOG_FORMAT  # timestamp
    assert "%(levelname)" in LOG_FORMAT  # log level
    assert "%(funcName)s" in LOG_FORMAT  # function name
    assert "%(lineno)d" in LOG_FORMAT  # line number
    assert "%(message)s" in LOG_FORMAT  # message


def test_console_handler_always_present():
    from app import logging_config

    logging_config._configured = False
    logging.getLogger().handlers.clear()

    logging_config.configure_logging()

    handler_types = {type(h) for h in logging.getLogger().handlers}
    assert logging.StreamHandler in handler_types or any(
        issubclass(t, logging.StreamHandler) for t in handler_types
    )


@pytest.fixture
def reset_logging():
    logging.getLogger().handlers.clear()
    yield
    from app import logging_config

    logging_config._configured = False
    logging.getLogger().handlers.clear()


def test_file_handler_present_when_env_is_local(monkeypatch, tmp_path, reset_logging):
    from app import logging_config
    from app.globals import Environment, settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "env", Environment.LOCAL)
    logging_config._configured = False

    logging_config.configure_logging()

    handler_types = {type(h) for h in logging.getLogger().handlers}
    assert any(issubclass(t, logging.FileHandler) for t in handler_types)
    assert (tmp_path / "logs" / "app.log").exists()


@pytest.mark.parametrize("env_value", ["stg", "prod"])
def test_file_handler_absent_when_env_is_not_local(
    monkeypatch, tmp_path, reset_logging, env_value
):
    from app import logging_config
    from app.globals import Environment, settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "env", Environment(env_value))
    logging_config._configured = False

    logging_config.configure_logging()

    handler_types = {type(h) for h in logging.getLogger().handlers}
    assert not any(issubclass(t, logging.FileHandler) for t in handler_types)
    assert not (tmp_path / "logs").exists()
