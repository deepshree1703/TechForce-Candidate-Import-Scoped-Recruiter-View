"""Creates the database engine and gives each request its own session."""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# One engine for the whole app. pool_pre_ping drops dead connections quietly.
engine = create_engine(settings.database_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine)


def get_session() -> Iterator[Session]:
    """Give one session to a request and always close it afterwards."""
    with SessionLocal() as session:
        yield session


def set_region_context(session: Session, regions: list[str]) -> None:
    """Tell PostgreSQL which regions this transaction may see (['*'] means all, for an admin).

    The value is sent as a bound parameter and lasts only until the transaction ends.
    The row-level security policies in db/schema.sql read it.
    """
    session.execute(
        text("SELECT set_config('app.regions', :regions, true)"),
        {"regions": ",".join(regions)},
    )