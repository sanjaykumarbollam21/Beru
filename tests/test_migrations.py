import os
import tempfile
import pytest
from sqlalchemy import create_engine, inspect, text
from hub.db import run_migrations

def test_alembic_migrations_apply_on_fresh_database():
    """
    Verify Alembic migrations apply cleanly from scratch to a fresh database,
    creating all expected tables and the alembic_version tracker.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    try:
        db_url = f"sqlite:///{db_path}"

        # 1. Apply Alembic migrations to fresh database
        run_migrations(db_url)

        # 2. Inspect created tables
        test_engine = create_engine(db_url)
        inspector = inspect(test_engine)
        table_names = set(inspector.get_table_names())

        expected_tables = {
            "alembic_version",
            "users",
            "devices",
            "pairing_codes",
            "user_preferences",
            "user_facts",
            "user_routines",
            "command_corrections",
            "skill_sequence_logs",
        }

        assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"

        # 3. Test insert and query on newly migrated tables
        with test_engine.connect() as conn:
            conn.execute(
                text("INSERT INTO users (id) VALUES (:id)"),
                {"id": "test-user-migrated"}
            )
            conn.commit()

            res = conn.execute(
                text("SELECT id FROM users WHERE id = :id"),
                {"id": "test-user-migrated"}
            ).scalar()
            assert res == "test-user-migrated"

    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass
