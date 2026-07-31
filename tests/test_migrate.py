import pytest
from sqlalchemy import create_engine, inspect

from app.db import migrate
from app.db.migrate import _split_sql_statements
from app.db.models.recipe import Recipe
from app.db.models.user import User


@pytest.fixture
def sqlite_engine(monkeypatch):
    """Swap the shared engine for an in-memory SQLite one for these tests.

    The real migrations use MySQL-only syntax (stored procedures/triggers),
    so these tests exercise the idempotency logic itself with generic SQL
    rather than the checked-in `.sql` files.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    monkeypatch.setattr(migrate, "engine", engine)
    return engine


def test_run_orm_migrations_creates_tables_and_is_idempotent(sqlite_engine):
    migrate.run_orm_migrations()
    migrate.run_orm_migrations()  # second run must not raise

    table_names = inspect(sqlite_engine).get_table_names()
    assert "recipes" in table_names
    assert "users" in table_names


def test_recipe_table_has_expected_index():
    index_names = {ix.name for ix in Recipe.__table__.indexes}
    assert "ix_recipes_owner_id" in index_names


def test_user_table_has_expected_unique_indexes():
    """Username and email must be unique (SCRUM-14's AC: 'Username must be Unique')."""
    indexes_by_name = {ix.name: ix for ix in User.__table__.indexes}
    assert indexes_by_name["ix_users_username"].unique is True
    assert indexes_by_name["ix_users_email"].unique is True


def test_run_sql_migrations_applies_each_file_once(monkeypatch, sqlite_engine, tmp_path):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "0001_create_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);"
    )
    monkeypatch.setattr(migrate, "SQL_MIGRATIONS_DIR", sql_dir)

    migrate.run_sql_migrations()
    assert migrate._applied_migrations(sqlite_engine) == {"0001_create_widgets.sql"}
    assert "widgets" in inspect(sqlite_engine).get_table_names()

    # Re-running must skip the already-applied file. `filename` is the
    # primary key of schema_migrations, so a re-insert would raise.
    migrate.run_sql_migrations()
    assert migrate._applied_migrations(sqlite_engine) == {"0001_create_widgets.sql"}


def test_run_sql_migrations_does_not_reapply_after_manual_insert(
    monkeypatch, sqlite_engine, tmp_path
):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "0001_create_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);"
    )
    monkeypatch.setattr(migrate, "SQL_MIGRATIONS_DIR", sql_dir)

    migrate._ensure_migrations_table(sqlite_engine)
    with sqlite_engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
            {"filename": "0001_create_widgets.sql"},
        )

    # Should skip cleanly rather than attempting (and failing) a duplicate insert.
    migrate.run_sql_migrations()
    assert "widgets" not in inspect(sqlite_engine).get_table_names()


def test_run_migrations_reapplies_orm_schema_after_sql_migrations(monkeypatch):
    """A raw SQL migration may need to drop/recreate an ORM-managed table (e.g.
    to apply a schema change create_all's checkfirst can't express on its
    own) -- see 0002_drop_recipe_stub_procedures.sql. run_migrations() must
    call run_orm_migrations() both before and after run_sql_migrations() so
    that table ends up recreated, not left missing."""
    call_order: list[str] = []
    monkeypatch.setattr(
        migrate, "run_orm_migrations", lambda: call_order.append("orm")
    )
    monkeypatch.setattr(
        migrate, "run_sql_migrations", lambda: call_order.append("sql")
    )

    migrate.run_migrations()

    assert call_order == ["orm", "sql", "orm"]


def test_splits_simple_statements():
    sql = "CREATE TABLE a (id INT);\nCREATE TABLE b (id INT);"
    statements = _split_sql_statements(sql)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE a")
    assert statements[1].startswith("CREATE TABLE b")


def test_keeps_begin_end_block_atomic():
    sql = (
        "CREATE PROCEDURE p()\n"
        "BEGIN\n"
        "    SELECT 1;\n"
        "    SELECT 2;\n"
        "END;\n"
        "CREATE TABLE t (id INT);"
    )
    statements = _split_sql_statements(sql)
    assert len(statements) == 2
    assert "BEGIN" in statements[0]
    assert statements[0].count(";") == 2  # the two inner SELECTs
    assert statements[1].startswith("CREATE TABLE t")


def test_ignores_comment_lines():
    sql = "-- a comment\nCREATE TABLE a (id INT);"
    statements = _split_sql_statements(sql)
    assert len(statements) == 1
