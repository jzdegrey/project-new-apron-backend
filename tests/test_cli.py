from typer.testing import CliRunner

from app.cli import cli

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "runserver" in result.output


def test_migrate_command_invokes_run_migrations(monkeypatch):
    calls = []
    monkeypatch.setattr("app.cli.run_migrations", lambda: calls.append(True))

    result = runner.invoke(cli, ["migrate"])

    assert result.exit_code == 0
    assert calls == [True]


def test_runserver_defaults_to_settings_host_and_port(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.cli.uvicorn.run",
        lambda app_path, **kwargs: captured.update(app_path=app_path, **kwargs),
    )

    result = runner.invoke(cli, ["runserver"])

    assert result.exit_code == 0
    assert captured["app_path"] == "app.main:app"
    assert captured["reload"] is False
    from app.globals import settings

    assert captured["host"] == settings.host
    assert captured["port"] == settings.port


def test_runserver_accepts_overrides(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.cli.uvicorn.run",
        lambda app_path, **kwargs: captured.update(app_path=app_path, **kwargs),
    )

    result = runner.invoke(
        cli, ["runserver", "--host", "127.0.0.1", "--port", "9000", "--reload"]
    )

    assert result.exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9000
    assert captured["reload"] is True
