"""Basic checks that the test database and the SQLAlchemy models match db/schema.sql."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import set_region_context
from app.models import Base


def test_database_is_utf8(app_session: Session) -> None:
    """Names with accents (Nguyễn, Sofía) need a UTF-8 database."""
    encoding = app_session.execute(
        text("SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = current_database()")
    ).scalar_one()
    assert encoding == "UTF8"


def test_unicode_names_come_back_unchanged(app_session: Session) -> None:
    """The Unicode name in the sample data is stored and read back exactly."""
    set_region_context(app_session, ["*"])
    names = app_session.execute(text("SELECT first_name, last_name FROM candidates WHERE candidate_id = 'T-3'"))
    assert names.one() == ("Nguyễn", "Thị Hoa")


def test_models_match_the_schema(app_engine: Engine) -> None:
    """Each model has the same table, columns and nullability as the real database."""
    inspector = inspect(app_engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)

    for table in Base.metadata.tables.values():
        real_columns = {column["name"]: column for column in inspector.get_columns(table.name)}
        assert set(real_columns) == {column.name for column in table.columns}, table.name
        for column in table.columns:
            assert real_columns[column.name]["nullable"] == column.nullable, f"{table.name}.{column.name}"