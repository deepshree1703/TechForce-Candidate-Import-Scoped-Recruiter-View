"""Pytest fixtures: a fresh test database built from the same db/schema.sql file.

The test database lives on the same Postgres server as the real one, under the name
<DB_NAME>_test. It is dropped and rebuilt at the start of every test run.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import read_env, settings
from app.models import Candidate, Recruiter

SCHEMA_FILE = Path(os.environ.get("SCHEMA_FILE", "/db/schema.sql"))
TEST_DB_NAME = f"{settings.db_name}_test"


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


def drop_test_database() -> None:
    """Drop the test database if it exists, even if something is still connected."""
    with connect_as_owner(settings.db_name) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB_NAME))
        )


@pytest.fixture(scope="session")
def test_database() -> Iterator[str]:
    """Create an empty test database, build it from schema.sql, and drop it at the end."""
    drop_test_database()
    with connect_as_owner(settings.db_name) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))
    with connect_as_owner(TEST_DB_NAME) as connection:
        connection.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    yield TEST_DB_NAME
    drop_test_database()


@pytest.fixture(scope="session")
def owner_engine(test_database: str) -> Iterator[Engine]:
    """An engine that logs in as the owner (a superuser, so row-level security is skipped)."""
    url = settings.build_url(read_env("DB_OWNER_USER"), read_env("DB_OWNER_PASSWORD"), test_database)
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def sample_data(owner_engine: Engine) -> None:
    """Put two recruiters and four candidates (one per region) into the test database."""
    people = [
        ("T-1", "Alicia", "Trent", "US-MW"),
        ("T-2", "Marcus", "Bellamy", "US-NE"),
        ("T-3", "Nguyễn", "Thị Hoa", "PH-MNL"),
        ("T-4", "Peter", "Vance", "US-W"),
    ]
    with Session(owner_engine) as session, session.begin():
        session.add_all(
            [
                Recruiter(
                    recruiter_id="R-1",
                    full_name="Test Admin",
                    email="admin@example.com",
                    role="admin",
                    assigned_regions=["*"],
                ),
                Recruiter(
                    recruiter_id="R-2",
                    full_name="Test Recruiter",
                    email="recruiter@example.com",
                    role="recruiter",
                    assigned_regions=["US-MW", "US-NE"],
                ),
            ]
        )
        session.add_all(
            [
                Candidate(
                    candidate_id=candidate_id,
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{candidate_id.lower()}@example.com",
                    region_code=region,
                    status="active",
                )
                for candidate_id, first_name, last_name, region in people
            ]
        )


@pytest.fixture(scope="session")
def app_engine(test_database: str, sample_data: None) -> Iterator[Engine]:
    """An engine that logs in as the limited API user, the way the real API does."""
    engine = create_engine(settings.database_url().set(database=test_database))
    yield engine
    engine.dispose()


@pytest.fixture
def app_session(app_engine: Engine) -> Iterator[Session]:
    """A session for the limited API user. Closing it rolls back anything the test did."""
    with Session(app_engine) as session:
        yield session