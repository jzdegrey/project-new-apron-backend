import logging

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
