"""Idempotent schema migrations.

Two layers, both safe to re-run:

1. ORM-managed schema (tables + indexes) via `Base.metadata.create_all`,
   which only creates objects that don't already exist.
2. Raw `.sql` files under `app/db/migrations/sql/` for anything the ORM
   can't express (stored procedures, triggers, ...). Each file is applied
   at most once, tracked in a `schema_migrations` table.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.session import engine
from app.logging_config import get_logger

logger = get_logger(__name__)

SQL_MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "sql"


def _ensure_migrations_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _applied_migrations(engine: Engine) -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT filename FROM schema_migrations"))
        return {row[0] for row in rows}


def _split_sql_statements(sql: str) -> list[str]:
    """Split on top-level `;` while treating BEGIN...END blocks as atomic."""
    statements: list[str] = []
    buffer: list[str] = []
    depth = 0

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        upper = stripped.upper()
        if upper.startswith("BEGIN"):
            depth += 1
        if upper.startswith("END"):
            depth = max(depth - 1, 0)
        if stripped.endswith(";") and depth == 0:
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []

    return statements


def run_orm_migrations() -> None:
    logger.info("Creating ORM-managed tables/indexes (checkfirst=True)")
    Base.metadata.create_all(bind=engine, checkfirst=True)


def run_sql_migrations() -> None:
    _ensure_migrations_table(engine)
    applied = _applied_migrations(engine)

    sql_files = sorted(SQL_MIGRATIONS_DIR.glob("*.sql")) if SQL_MIGRATIONS_DIR.exists() else []
    for sql_file in sql_files:
        if sql_file.name in applied:
            logger.info("Skipping already-applied migration %s", sql_file.name)
            continue

        logger.info("Applying migration %s", sql_file.name)
        statements = _split_sql_statements(sql_file.read_text())
        with engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
                {"filename": sql_file.name},
            )


def run_migrations() -> None:
    run_orm_migrations()
    run_sql_migrations()
    # Re-run so a raw SQL migration that drops/recreates an ORM-managed table
    # (e.g. to apply a schema change create_all's checkfirst can't express)
    # leaves that table restored before this call returns. A no-op otherwise,
    # since checkfirst skips anything already present.
    run_orm_migrations()
    logger.info("Migrations complete")
