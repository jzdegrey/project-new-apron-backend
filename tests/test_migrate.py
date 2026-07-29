from app.db.migrate import _split_sql_statements


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
