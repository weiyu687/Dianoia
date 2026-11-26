"""Versioned schema setup: python -m app.migrate, before production startup."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .db import engine

HEAD = "20261126_05"


def migrate():
    configuration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        elif engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(43160261119)"))
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "head")
        connection.commit()


def initialize_database():
    if engine.dialect.name == "sqlite":
        migrate()
    else:
        with engine.connect() as connection:
            ready = "alembic_version" in inspect(connection).get_table_names()
            if not ready or connection.scalar(text("SELECT version_num FROM alembic_version")) != HEAD:
                raise RuntimeError("Run python -m app.migrate before starting the service")


if __name__ == "__main__":
    migrate()
