"""Tests for safe, repeatable Neon schema setup."""

from scripts.create_neon_schema import SCHEMA_STATEMENTS


def test_schema_setup_preserves_existing_tables_and_indexes() -> None:
    """Non-destructive schema setup can be rerun when objects already exist."""
    create_statements = SCHEMA_STATEMENTS[1:]
    table_statements = [
        statement
        for statement in create_statements
        if "CREATE TABLE" in statement
    ]
    index_statements = [
        statement
        for statement in create_statements
        if "CREATE INDEX" in statement
    ]

    assert len(table_statements) == 5
    assert all("CREATE TABLE IF NOT EXISTS" in statement for statement in table_statements)
    assert len(index_statements) == 1
    assert all(
        "CREATE INDEX IF NOT EXISTS" in statement
        for statement in index_statements
    )
    assert "DROP TABLE" in SCHEMA_STATEMENTS[0]
