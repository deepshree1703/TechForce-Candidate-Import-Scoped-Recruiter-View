"""Fixtures for the API tests.

They use their own database, built from the same db/schema.sql file, so they never touch
the data the schema tests count. The real data/recruiters.csv is loaded as the recruiters,
and the API is called through a test client that logs in to this database as the limited
API user, exactly like the real API.

The app and the test client are imported inside the fixtures, so a problem there shows up
as an error in these tests only and does not stop the other tests from being collected.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import read_env, settings
from app.database import get_session
from app.seed import read_recruiters, save_recruiters

SCHEMA_FILE = Path(os.environ.get("SCHEMA_FILE", "/db/schema.sql"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
API_DB_NAME = f"{settings.db_name}_api_test"


def connect_as_owner(database: str) -> psycopg.Connection:
    """Open an autocommit connection as the owner login (needed to create a database)."""
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=database,
        user=read_env("DB_OWNER_USER"),
        password=read_env("DB_OWNER_PASSWORD"),
        autocommit=True,
    )


def drop_api_database() -> None:
    """Drop the API test database if it exists, even if something is still connected."""
    with connect_as_owner(settings.db_name) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(API_DB_NAME))
        )


@pytest.fixture(scope="session")
def api_database() -> Iterator[str]:
    """Create an empty database, build it from schema.sql, and drop it at the end."""
    drop_api_database()
    with connect_as_owner(settings.db_name) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(API_DB_NAME)))
    with connect_as_owner(API_DB_NAME) as connection:
        connection.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    yield API_DB_NAME
    drop_api_database()


@pytest.fixture(scope="session")
def api_owner_engine(api_database: str) -> Iterator[Engine]:
    """An owner engine, which sees every row. Used to set up and to look at what was stored."""
    url = settings.build_url(read_env("DB_OWNER_USER"), read_env("DB_OWNER_PASSWORD"), api_database)
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def api_app_engine(api_database: str) -> Iterator[Engine]:
    """An engine that logs in as the limited API user, as the real API does."""
    engine = create_engine(settings.database_url().set(database=api_database))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def real_recruiters(api_owner_engine: Engine) -> None:
    """Load the real data/recruiters.csv with the same code the seed uses."""
    path = DATA_DIR / "recruiters.csv"
    if not path.exists():
        pytest.fail(f"{path} not found. Put recruiters.csv in the data folder.")
    with Session(api_owner_engine) as session, session.begin():
        save_recruiters(session, read_recruiters(path))


@pytest.fixture(scope="session")
def real_csv() -> bytes:
    """The bytes of the real data/candidates_import.csv file."""
    path = DATA_DIR / "candidates_import.csv"
    if not path.exists():
        pytest.fail(f"{path} not found. Put candidates_import.csv in the data folder.")
    return path.read_bytes()


@pytest.fixture
def oversized_body() -> bytes:
    """A body one byte over the upload size limit."""
    from app.routes.imports import MAX_UPLOAD_BYTES

    return b"x" * (MAX_UPLOAD_BYTES + 1)


@pytest.fixture
def client(api_app_engine: Engine, api_owner_engine: Engine, real_recruiters: None) -> Iterator[Any]:
    """A test client wired to the API test database, starting every test with no candidates."""
    from fastapi.testclient import TestClient

    from app.main import app

    with api_owner_engine.begin() as connection:
        connection.execute(text("TRUNCATE candidates, import_runs RESTART IDENTITY"))

    def test_session() -> Iterator[Session]:
        """Give each request a session that logs in as the limited API user on the test database."""
        with Session(api_app_engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    yield TestClient(app)
    app.dependency_overrides.clear()