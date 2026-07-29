"""CLI entrypoint. Run with `python -m app.cli <command>`."""

import typer
import uvicorn

from app.db.migrate import run_migrations
from app.globals import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

cli = typer.Typer(help="Project New Apron backend CLI")


@cli.command()
def migrate() -> None:
    """Apply all pending database migrations (tables, indexes, procedures, triggers)."""
    run_migrations()


@cli.command()
def runserver(
    host: str = typer.Option(None, help="Defaults to settings.host"),
    port: int = typer.Option(None, help="Defaults to settings.port"),
    reload: bool = typer.Option(False, help="Enable autoreload (local dev only)"),
) -> None:
    """Run the FastAPI app with uvicorn."""
    uvicorn.run(
        "app.main:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


if __name__ == "__main__":
    cli()
